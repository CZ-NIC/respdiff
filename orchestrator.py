#!/usr/bin/env python3

import argparse
import logging
from multiprocessing import pool
import sys

from respdiff import cli, sendrecv
from respdiff.database import LMDB, MetaDatabase


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description="read queries from LMDB, send them in parallel to servers "
        "listed in configuration file, and record answers into LMDB"
    )
    cli.add_arg_envdir(parser)
    cli.add_arg_config(parser)
    parser.add_argument(
        "--ignore-timeout",
        action="store_true",
        help="continue despite consecutive timeouts from resolvers",
    )

    args = parser.parse_args()
    sendrecv.module_init(args)

    with LMDB(args.envdir) as lmdb:
        meta = MetaDatabase(lmdb, args.cfg["servers"]["names"], create=True)
        meta.write_version()
        meta.write_start_time()

        lmdb.open_db(LMDB.QUERIES)
        adb = lmdb.open_db(LMDB.ANSWERS, create=True, check_notexists=True)

        qstream = lmdb.key_value_stream(LMDB.QUERIES)
        txn = lmdb.env.begin(adb, write=True)
        try:
            # process queries in parallel
            with pool.Pool(
                processes=args.cfg["sendrecv"]["jobs"], initializer=sendrecv.worker_init
            ) as p:
                i = 0
                for qkey, blob in p.imap_unordered(
                    sendrecv.worker_perform_query, qstream, chunksize=100
                ):
                    i += 1
                    if i % 10000 == 0:
                        logging.info("Received {:d} answers".format(i))
                    txn.put(qkey, blob)
        except KeyboardInterrupt:
            logging.info("SIGINT received, exiting...")
            sys.exit(130)
        except RuntimeError as err:
            logging.error(err)
            sys.exit(1)
        finally:
            # attempt to preserve data if something went wrong (or not)
            logging.debug("Comitting LMDB transaction...")
            txn.commit()
            meta.write_end_time()


if __name__ == "__main__":
    main()
