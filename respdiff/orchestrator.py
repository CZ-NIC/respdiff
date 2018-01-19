#!/usr/bin/env python3

import argparse
import multiprocessing.pool as pool
import pickle
import sys
import threading
import time
import logging

import lmdb

import cfg
import dbhelper
import sendrecv


worker_state = {}  # shared by all workers
resolvers = []
timeout = None


def worker_init():
    """
    make sure it works with distincts processes and threads as well
    """
    tid = threading.current_thread().ident
    selector, sockets = sendrecv.sock_init(resolvers)
    worker_state[tid] = (selector, sockets)


def worker_deinit(selector, sockets):
    """
    Close all sockets and selector.
    """
    selector.close()
    for _, sck, _ in sockets:
        sck.close()


def worker_query_lmdb_wrapper(args):
    qid, qwire = args

    tid = threading.current_thread().ident
    selector, sockets = worker_state[tid]

    replies, reinit = sendrecv.send_recv_parallel(qwire, selector, sockets, timeout)
    if reinit:  # a connection is broken or something
        # TODO: log this?
        worker_deinit(selector, sockets)
        worker_init()

    blob = pickle.dumps(replies)
    return (qid, blob)


def lmdb_init(envdir):
    """Open LMDB environment and database for writting."""
    config = dbhelper.env_open.copy()
    config.update({
        'path': envdir,
        'writemap': True,
        'sync': False,
        'map_async': True,
        'readonly': False
    })
    lenv = lmdb.Environment(**config)
    qdb = lenv.open_db(key=dbhelper.QUERIES_DB_NAME,
                       create=False,
                       **dbhelper.db_open)
    adb = lenv.open_db(key=dbhelper.ANSWERS_DB_NAME, create=True, **dbhelper.db_open)
    sdb = lenv.open_db(key=dbhelper.STATS_DB_NAME, create=True, **dbhelper.db_open)
    return (lenv, qdb, adb, sdb)


def main():
    global timeout

    parser = argparse.ArgumentParser(
        description='read queries from LMDB, send them in parallel to servers '
                    'listed in configuration file, and record answers into LMDB')
    parser.add_argument('-c', '--config', type=cfg.read_cfg, default='respdiff.cfg', dest='cfg',
                        help='config file (default: respdiff.cfg)')
    parser.add_argument('envdir', type=str,
                        help='LMDB environment to read queries from and to write answers to')
    args = parser.parse_args()

    for resname in args.cfg['servers']['names']:
        rescfg = args.cfg[resname]
        resolvers.append((resname, rescfg['ip'], rescfg['transport'], rescfg['port']))

    timeout = args.cfg['sendrecv']['timeout']

    if not dbhelper.db_exists(args.envdir, dbhelper.QUERIES_DB_NAME):
        logging.critical(
            'LMDB environment "%s does not contain DB %s! '
            'Use qprep to prepare queries.',
            args.envdir, dbhelper.ANSWERS_DB_NAME)
        sys.exit(1)

    if dbhelper.db_exists(args.envdir, dbhelper.ANSWERS_DB_NAME):
        logging.critical(
            'LMDB environment "%s" already contains DB %s! '
            'Overwritting it would invalidate data in the environment, '
            'terminating.',
            args.envdir, dbhelper.ANSWERS_DB_NAME)
        sys.exit(1)

    lenv, qdb, adb, sdb = lmdb_init(args.envdir)
    qstream = dbhelper.key_value_stream(lenv, qdb)
    stats = {
        'start_time': time.time(),
        'end_time': None,
    }

    with lenv.begin(adb, write=True) as txn:
        with pool.Pool(
                processes=args.cfg['sendrecv']['jobs'],
                initializer=worker_init) as p:
            for qid, blob in p.imap(worker_query_lmdb_wrapper, qstream, chunksize=100):
                txn.put(qid, blob)

    stats['end_time'] = time.time()
    with lenv.begin(sdb, write=True) as txn:
        txn.put(b'global_stats', pickle.dumps(stats))


if __name__ == "__main__":
    main()
