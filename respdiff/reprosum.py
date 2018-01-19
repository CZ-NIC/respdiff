import pickle
import sys

import dns.message
import lmdb

import dbhelper
from msgdiff import DataMismatch  # noqa: needed for unpickling


def open_db(envdir):
    config = dbhelper.env_open.copy()
    config.update({
        'path': envdir,
        'readonly': False,
        'create': False
    })
    lenv = lmdb.Environment(**config)
    qdb = lenv.open_db(key=b'queries', create=False, **dbhelper.db_open)
    ddb = lenv.open_db(key=b'diffs', create=False, **dbhelper.db_open)
    reprodb = lenv.open_db(key=b'reprostats', create=True, **dbhelper.db_open)
    return lenv, qdb, ddb, reprodb


def load_stats(lenv, reprodb, qid):
    """(count, others_agreed, diff_matched)"""
    with lenv.begin() as txn:
        stats_bin = txn.get(qid, db=reprodb)
    if stats_bin:
        stats = pickle.loads(stats_bin)
    else:
        stats = (0, 0, 0)

    assert len(stats) == 3
    assert stats[0] >= stats[1] >= stats[2]
    return stats[0], stats[1], stats[2]


def read_repro_lmdb(levn, qdb, reprodb):
    with levn.begin() as txn:
        with txn.cursor(reprodb) as diffcur:
            for qid, reproblob in diffcur:
                (count, others_agreed, diff_matched) = pickle.loads(reproblob)
                qwire = txn.get(qid, db=qdb)
                yield (qid, qwire, (count, others_agreed, diff_matched))


def main():
    lenv, qdb, _, reprodb = open_db(sys.argv[1])
    repro_stream = read_repro_lmdb(lenv, qdb, reprodb)
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
