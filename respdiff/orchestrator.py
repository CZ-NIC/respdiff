#!/usr/bin/env python3

import argparse
import logging
import multiprocessing.pool as pool
import pickle
import random
import threading
import time
from typing import List, Tuple, Dict, Any  # noqa: type hints
import sys

import cfg
from dbhelper import LMDB
import sendrecv


worker_state = threading.local()

resolvers = []  # type: List[Tuple[str, str, str, int]]
ignore_timeout = False
max_timeouts = 10  # crash when N consecutive timeouts are received from a single resolver
timeout = None
time_delay_min = 0
time_delay_max = 0


def worker_init():
    """
    make sure it works with distincts processes and threads as well
    """
    worker_state.timeouts = {}
    worker_reinit()


def worker_reinit():
    selector, sockets = sendrecv.sock_init(resolvers)
    worker_state.selector = selector
    worker_state.sockets = sockets


def worker_deinit(selector, sockets):
    """
    Close all sockets and selector.
    """
    selector.close()
    for _, sck, _ in sockets:
        sck.close()


def worker_query_lmdb_wrapper(args):
    qid, qwire = args

    selector = worker_state.selector
    sockets = worker_state.sockets

    # optional artificial delay for testing
    if time_delay_max > 0:
        time.sleep(random.uniform(time_delay_min, time_delay_max))

    replies, reinit = sendrecv.send_recv_parallel(qwire, selector, sockets, timeout)
    if not ignore_timeout:
        check_timeout(replies)

    if reinit:  # a connection is broken or something
        # TODO: log this?
        worker_deinit(selector, sockets)
        worker_reinit()

    blob = pickle.dumps(replies)
    return (qid, blob)


def check_timeout(replies):
    for resolver, reply in replies.items():
        timeouts = worker_state.timeouts
        if reply.wire is not None:
            timeouts[resolver] = 0
        else:
            timeouts[resolver] = timeouts.get(resolver, 0) + 1
            if timeouts[resolver] >= max_timeouts:
                raise RuntimeError(
                    "Resolver '{}' timed-out {:d} times in a row. "
                    "Use '--ignore-timeout' to supress this error.".format(
                        resolver, max_timeouts))


def main():
    global ignore_timeout
    global max_timeouts
    global timeout
    global time_delay_min
    global time_delay_max

    logging.basicConfig(format='%(levelname)s %(message)s', level=logging.INFO)

    parser = argparse.ArgumentParser(
        description='read queries from LMDB, send them in parallel to servers '
                    'listed in configuration file, and record answers into LMDB')
    parser.add_argument('-c', '--config', type=cfg.read_cfg, default='respdiff.cfg', dest='cfg',
                        help='config file (default: respdiff.cfg)')
    parser.add_argument('--ignore-timeout', action="store_true",
                        help='continue despite consecutive timeouts from resolvers')
    parser.add_argument('envdir', type=str,
                        help='LMDB environment to read queries from and to write answers to')
    args = parser.parse_args()

    for resname in args.cfg['servers']['names']:
        rescfg = args.cfg[resname]
        resolvers.append((resname, rescfg['ip'], rescfg['transport'], rescfg['port']))

    ignore_timeout = args.ignore_timeout
    timeout = args.cfg['sendrecv']['timeout']
    time_delay_min = args.cfg['sendrecv']['time_delay_min']
    time_delay_max = args.cfg['sendrecv']['time_delay_max']
    try:
        max_timeouts = args.cfg['sendrecv']['max_timeouts']
    except KeyError:
        pass
    stats = {
        'start_time': time.time(),
        'end_time': None,
    }

    with LMDB(args.envdir) as lmdb:
        lmdb.open_db(LMDB.QUERIES)
        adb = lmdb.open_db(LMDB.ANSWERS, create=True, check_notexists=True)
        sdb = lmdb.open_db(LMDB.STATS, create=True)

        qstream = lmdb.key_value_stream(LMDB.QUERIES)
        txn = lmdb.env.begin(adb, write=True)
        try:
            # process queries in parallel
            with pool.Pool(
                    processes=args.cfg['sendrecv']['jobs'],
                    initializer=worker_init) as p:
                i = 0
                for qid, blob in p.imap(worker_query_lmdb_wrapper, qstream,
                                        chunksize=100):
                    i += 1
                    if i % 10000 == 0:
                        logging.info('Received {:d} answers'.format(i))
                    txn.put(qid, blob)
        except RuntimeError as err:
            logging.error(err)
            sys.exit(1)
        finally:
            # attempt to preserve data if something went wrong (or not)
            txn.commit()

            stats['end_time'] = time.time()
            with lmdb.env.begin(sdb, write=True) as txn:
                txn.put(b'global_stats', pickle.dumps(stats))


if __name__ == "__main__":
    main()
