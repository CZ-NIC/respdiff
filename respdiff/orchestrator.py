#!/usr/bin/env python3

import argparse
import multiprocessing.pool as pool
import pickle
import sys
import threading
import logging

import lmdb

import cfg
import dbhelper
import sendrecv


global worker_state
worker_state = {}  # shared by all workers


def worker_init(init_resolvers, init_timeout):
    """
    make sure it works with distincts processes and threads as well
    """
    global worker_state  # initialized to empty dict
    global resolvers
    global timeout
    resolvers = init_resolvers
    timeout = init_timeout

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
    global worker_state  # initialized in worker_init
    global timeout
    qid, qwire = args

    tid = threading.current_thread().ident
    selector, sockets = worker_state[tid]

    replies, reinit = sendrecv.send_recv_parallel(qwire, selector, sockets, timeout)
    if reinit:  # a connection is broken or something
        # TODO: log this?
        worker_deinit(selector, sockets)
        worker_init(resolvers, timeout)

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
    return (lenv, qdb, adb)


def main():
    parser = argparse.ArgumentParser(
        description='read queries from LMDB, send them in parallel to servers '
                    'listed in configuration file, and record answers into LMDB')
    parser.add_argument('-c', '--config', type=cfg.read_cfg, default='respdiff.cfg', dest='cfg',
                        help='config file (default: respdiff.cfg)')
    parser.add_argument('envdir', type=str,
                        help='LMDB environment to read queries from and to write answers to')
    args = parser.parse_args()

    resolvers = []
    for resname in args.cfg['servers']['names']:
        rescfg = args.cfg[resname]
        resolvers.append((resname, rescfg['ip'], rescfg['transport'], rescfg['port']))

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

    lenv, qdb, adb = lmdb_init(args.envdir)
    qstream = dbhelper.key_value_stream(lenv, qdb)

    with lenv.begin(adb, write=True) as txn:
        with pool.Pool(
                processes=args.cfg['sendrecv']['jobs'],
                initializer=worker_init,
                initargs=[resolvers, args.cfg['sendrecv']['timeout']]) as p:
            for qid, blob in p.imap(worker_query_lmdb_wrapper, qstream, chunksize=100):
                txn.put(qid, blob)


if __name__ == "__main__":
    main()
