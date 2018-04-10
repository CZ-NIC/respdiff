#!/usr/bin/env python3

import argparse
import logging
import multiprocessing.pool as pool
import os
import time
import sys

import cli
from dataformat import DiffReport
from dbhelper import LMDB
import sendrecv


def export_statistics(lmdb, datafile, start_time):
    qdb = lmdb.get_db(LMDB.QUERIES)
    adb = lmdb.get_db(LMDB.ANSWERS)
    with lmdb.env.begin() as txn:
        total_queries = txn.stat(qdb)['entries']
        total_answers = txn.stat(adb)['entries']
    report = DiffReport(
        start_time,
        int(time.time()),
        total_queries,
        total_answers)

    # it doesn't make sense to use existing report.json in orchestrator
    if os.path.exists(datafile):
        backup_filename = datafile + '.bak'
        os.rename(datafile, backup_filename)
        logging.warning(
            'JSON report already exists, overwriting file. Original '
            'file backed up as %s', backup_filename)
    report.export_json(datafile)


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description='read queries from LMDB, send them in parallel to servers '
                    'listed in configuration file, and record answers into LMDB')
    cli.add_arg_envdir(parser)
    cli.add_arg_config(parser)
    cli.add_arg_datafile(parser)
    parser.add_argument('--ignore-timeout', action="store_true",
                        help='continue despite consecutive timeouts from resolvers')

    args = parser.parse_args()
    sendrecv.module_init(args)
    datafile = cli.get_datafile(args, check_exists=False)
    start_time = int(time.time())

    with LMDB(args.envdir) as lmdb:
        lmdb.open_db(LMDB.QUERIES)
        adb = lmdb.open_db(LMDB.ANSWERS, create=True, check_notexists=True)

        qstream = lmdb.key_value_stream(LMDB.QUERIES)
        txn = lmdb.env.begin(adb, write=True)
        try:
            # process queries in parallel
            with pool.Pool(
                    processes=args.cfg['sendrecv']['jobs'],
                    initializer=sendrecv.worker_init) as p:
                i = 0
                for qkey, blob in p.imap(sendrecv.worker_perform_query, qstream,
                                         chunksize=100):
                    i += 1
                    if i % 10000 == 0:
                        logging.info('Received {:d} answers'.format(i))
                    txn.put(qkey, blob)
        except RuntimeError as err:
            logging.error(err)
            sys.exit(1)
        finally:
            # attempt to preserve data if something went wrong (or not)
            txn.commit()

            # get query/answer statistics
            export_statistics(lmdb, datafile, start_time)


if __name__ == "__main__":
    main()
