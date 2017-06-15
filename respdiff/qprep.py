import multiprocessing.pool as pool
import sys

import lmdb

import dbhelper
import qtext


def read_text():
    i = 0
    for line in sys.stdin:
        line = line.strip()
        if line:
            i += 1
            yield (i, line)


def gen_q(qstr):
    try:
        qry = qtext.qfromtext(qstr.split())
    except BaseException:
        print('line malformed: %s' % qstr)
        return
    if qtext.is_blacklisted(qry):
        return
    return qry.to_wire()


def write_lmdb(qid, wire):
    """
    Worker: write query wire format into database
    """
    global env
    global db

    key = dbhelper.qid2key(qid)
    with env.begin(db, write=True) as txn:
        txn.put(key, wire)


def lmdb_init(envdir):
    """
    Worker: initialize LMDB env and open 'queries' database
    """
    global env
    global db

    config = dbhelper.env_open.copy()
    config.update({
        'path': envdir,
        'sync': False,    # unsafe but fast
        'writemap': True  # we do not care, this is a new database
        })
    env = lmdb.Environment(**config)
    db = env.open_db(key=b'queries', **dbhelper.db_open)


def gen_wrapper_lmdb(args):
    qid, qstr = args
    wire = gen_q(qstr)
    write_lmdb(qid, wire)

def main():
    qstream = read_text()
    with pool.Pool(initializer=lmdb_init, initargs=(sys.argv[1],)) as workers:
        for _ in workers.imap_unordered(gen_wrapper_lmdb, qstream, chunksize=1000):
            pass

if __name__ == '__main__':
    main()
