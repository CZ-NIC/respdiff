import multiprocessing.dummy as pool
import os
import pickle
import sys
import threading

import lmdb

import lmdbcfg
import sendrecv

timeout = 5
resolvers = [
        ('kresd', '127.0.0.1', 5353),
        ('unbound', '127.0.0.1', 53535),
        ('bind', '127.0.0.1', 53533)
    ]

# find query files

global worker_state
worker_state = {}  # shared by all workers

def worker_init(envdir, resolvers, init_timeout):
    """
    make sure it works with distincts processes and threads as well
    """
    global worker_state  # initialized to empty dict
    global timeout
    timeout = init_timeout
    tid = threading.current_thread().ident
    selector, sockets = sendrecv.sock_init(resolvers)

    config = lmdbcfg.env_open.copy()
    config.update({
        'path': envdir,
        'writemap': True,
        'readonly': False
        })
    lenv = lmdb.Environment(**config)
    adb = lenv.open_db(key=b'answers', create=True, **lmdbcfg.db_open)

    worker_state[tid] = (lenv, adb, selector, sockets)

def worker_query_lmdb_wrapper(args):
    global worker_state  # initialized in worker_init
    global timeout
    qid, qwire = args
    tid = threading.current_thread().ident
    lenv, adb, selector, sockets = worker_state[tid]

    replies = sendrecv.send_recv_parallel(qwire, selector, sockets, timeout)
    blob = pickle.dumps(replies)
    with lenv.begin(adb, write=True) as txn:
        txn.put(qid, blob)

def read_queries_lmdb(lenv, qdb):
    with lenv.begin(qdb) as txn:
        cur = txn.cursor(qdb)
        for qid, qwire in cur:
            yield (qid, qwire)

#selector.close()  # TODO

# init LMDB
def reader_init(envdir):
    config = lmdbcfg.env_open.copy()
    config.update({
        'path': envdir,
        'readonly': True
        })
    lenv = lmdb.Environment(**config)
    qdb = lenv.open_db(key=b'queries', **lmdbcfg.db_open, create=False)
    return (lenv, qdb)

def main():
    envdir = sys.argv[1]
    lenv, qdb = reader_init(envdir)
    qstream = read_queries_lmdb(lenv, qdb)

    with pool.Pool(
            processes=4,
            initializer=worker_init,
            initargs=[envdir, resolvers, timeout]) as p:
        for i in p.imap_unordered(worker_query_lmdb_wrapper, qstream, chunksize=10):
            pass

if __name__ == "__main__":
    main()
