import pickle
import subprocess
import sys

from dbhelper import LMDB
import diffsum
from msgdiff import DataMismatch  # noqa: needed for unpickling
import msgdiff
import orchestrator
import sendrecv


def load_stats(lmdb, qid):
    """(count, others_agreed, diff_matched)"""
    reprodb = lmdb.get_db(LMDB.REPROSTATS)
    with lmdb.env.begin(reprodb) as txn:
        stats_bin = txn.get(qid)
    if stats_bin:
        stats = pickle.loads(stats_bin)
    else:
        stats = (0, 0, 0)

    assert len(stats) == 3
    assert stats[0] >= stats[1] >= stats[2]
    return stats[0], stats[1], stats[2]


def save_stats(lmdb, qid, stats):
    assert len(stats) == 3
    assert stats[0] >= stats[1] >= stats[2]

    stats_bin = pickle.dumps(stats)
    reprodb = lmdb.get_db(LMDB.REPROSTATS)
    with lmdb.env.begin(reprodb, write=True) as txn:
        txn.put(qid, stats_bin)


def main():
    criteria = [
        'opcode', 'rcode', 'flags', 'question', 'qname', 'qtype', 'answertypes', 'answerrrsigs'
    ]  # FIXME
    selector, sockets = sendrecv.sock_init(getattr(orchestrator, 'resolvers'))

    with LMDB(sys.argv[1]) as lmdb:
        lmdb.open_db(LMDB.QUERIES)
        lmdb.open_db(LMDB.DIFFS)
        lmdb.open_db(LMDB.REPROSTATS, create=True)

        diff_stream = diffsum.read_diffs_lmdb(lmdb)
        processed = 0
        verified = 0
        for qid, qwire, orig_others_agree, orig_diffs in diff_stream:
            if not orig_others_agree:
                continue  # others do not agree, nothing to verify

            # others agree, verify if answers are stable and the diff is reproducible
            retries, upstream_stable, diff_matches = load_stats(lmdb, qid)
            if retries > 0:
                if retries != upstream_stable or upstream_stable != diff_matches:
                    continue  # either unstable upstream or diff is not 100 % reproducible, skip it
            processed += 1

            # it might be reproducible, restart everything
            if len(sys.argv) == 3:
                subprocess.check_call([sys.argv[2]])

            wire_blobs = sendrecv.send_recv_parallel(qwire, selector, sockets, orchestrator.timeout)
            answers = msgdiff.decode_wire_dict(wire_blobs)
            new_others_agree, new_diffs = msgdiff.compare(answers, criteria, 'kresd')  # FIXME

            retries += 1
            if orig_others_agree == new_others_agree:
                upstream_stable += 1
                if orig_diffs == new_diffs:
                    diff_matches += 1
            print(qid, (retries, upstream_stable, diff_matches))
            save_stats(lmdb, qid, (retries, upstream_stable, diff_matches))
            if retries == upstream_stable == diff_matches:
                verified += 1

    print('processed :', processed)
    print('verified  :', verified)
    print('falzified : {}    {:6.2f} %'.format(
        processed - verified, 100.0 * (processed - verified) / processed))


if __name__ == '__main__':
    main()
