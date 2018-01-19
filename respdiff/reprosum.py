import pickle
import sys

import dns.message

from dbhelper import LMDB
from msgdiff import DataMismatch  # noqa: needed for unpickling


def read_repro_lmdb(lmdb):
    qdb = lmdb.get_db(LMDB.QUERIES)
    reprodb = lmdb.get_db(LMDB.REPROSTATS)
    with lmdb.env.begin() as txn:
        with txn.cursor(reprodb) as diffcur:
            for qid, reproblob in diffcur:
                count, others_agreed, diff_matched = pickle.loads(reproblob)
                qwire = txn.get(qid, db=qdb)
                yield qid, qwire, (count, others_agreed, diff_matched)


def main():
    with LMDB(sys.argv[1]) as lmdb:
        lmdb.open_db(LMDB.QUERIES)
        lmdb.open_db(LMDB.DIFFS)
        lmdb.open_db(LMDB.REPROSTATS, create=True)

        repro_stream = read_repro_lmdb(lmdb)
        for _, qwire, (count, others_agreed, diff_matched) in repro_stream:
            if not count == others_agreed == diff_matched:
                continue
            try:
                qmsg = dns.message.from_wire(qwire)
            except Exception:
                continue
            print(qmsg.question[0])


if __name__ == '__main__':
    main()
