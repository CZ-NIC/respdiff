#!/usr/bin/env python3

import argparse
import multiprocessing.pool as pool
import pickle
import threading
import time
from typing import List, Tuple  # noqa: type hints

import cfg
from dbhelper import LMDB
import sendrecv


worker_state = {}  # shared by all workers
resolvers = []  # type: List[Tuple[str, str, str, int]]
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
    stats = {
        'start_time': time.time(),
        'end_time': None,
    }

    with LMDB(args.envdir, fast=True) as lmdb:
        lmdb.open_db(LMDB.QUERIES, check_exists=True)
        adb = lmdb.open_db(LMDB.ANSWERS, create=True, check_notexists=True)
        sdb = lmdb.open_db(LMDB.STATS, create=True)

        qstream = lmdb.key_value_stream(LMDB.QUERIES)
        with lmdb.env.begin(adb, write=True) as txn:
            with pool.Pool(
                    processes=args.cfg['sendrecv']['jobs'],
                    initializer=worker_init) as p:
                for qid, blob in p.imap(worker_query_lmdb_wrapper, qstream, chunksize=100):
                    txn.put(qid, blob)

        stats['end_time'] = time.time()
        with lmdb.env.begin(sdb, write=True) as txn:
            txn.put(b'global_stats', pickle.dumps(stats))


if __name__ == "__main__":
    main()
