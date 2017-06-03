import itertools
import multiprocessing.pool as pool
import errno
from pprint import pprint
import os
import sys

import lmdb

import dbhelper
import makeq


def read_text():
    i = 0
    for line in sys.stdin:
        line = line.strip()
        if line:
            i += 1
            yield (i, line)
            if i % 10000 == 0:
                print(i)
            #if i > 770000:
            #    print(line)

def gen_q(qtext):
    try:
        qry = makeq.qfromtext(qtext.split())
    except BaseException:
        print('line malformed: %s' % qtext)
        return
    if makeq.is_blacklisted(qry):
        return
    return qry.to_wire()


def write_file(qid, wire):
    dirname = '%09d' % qid
    qfilename = '%s/q.dns' % dirname
    try:
        os.mkdir(dirname)
    except OSError as ex:
        if not ex.errno == errno.EEXIST:
            raise
    with open(qfilename, 'wb') as qfile:
        qfile.write(wire)


def write_lmdb(qid, wire):
    global env
    global db

    key = str(qid).encode('ascii')
    with env.begin(db, write=True) as txn:
        txn.put(key, wire)


def lmdb_init(envdir):
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
    qid, qtext = args
    wire = gen_q(qtext)
    write_lmdb(qid, wire)

def main():
    qstream = itertools.islice(read_text(), 1000000)
    #qstream = read_text()
    #for i in map(gen_qfile, qstream):
    #    pass
    with pool.Pool(initializer=lmdb_init, initargs=(sys.argv[1],)) as p:
        for i in p.imap_unordered(gen_wrapper_lmdb, qstream, chunksize=1000):
            pass

    # LMDB specifics
    lmdb_init(sys.argv[1])
    pprint(env.info())
    env.close()

if __name__ == '__main__':
    main()

