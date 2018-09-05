#!/usr/bin/env python3

import argparse
import logging
import sys
from typing import (  # noqa
    Any, AbstractSet, Iterable, Iterator, Mapping, Sequence, Tuple, TypeVar,
    Union)

from respdiff import cli, repro, sendrecv
from respdiff.database import DNSRepliesFactory, LMDB, MetaDatabase
from respdiff.dataformat import Diff, DiffReport, FieldLabel, ReproData, QID  # noqa


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description='attempt to reproduce original diffs from JSON report')
    cli.add_arg_envdir(parser)
    cli.add_arg_config(parser)
    cli.add_arg_datafile(parser)
    parser.add_argument('--sequential', action='store_true', default=False,
                        help='send one query at a time (slower, but more reliable)')

    args = parser.parse_args()
    sendrecv.module_init(args)
    datafile = cli.get_datafile(args)
    report = DiffReport.from_json(datafile)
    restart_scripts = repro.get_restart_scripts(args.cfg)
    servers = args.cfg['servers']['names']
    dnsreplies_factory = DNSRepliesFactory(servers)

    if args.sequential:
        nproc = 1
    else:
        nproc = args.cfg['sendrecv']['jobs']

    if report.reprodata is None:
        report.reprodata = ReproData()

    with LMDB(args.envdir, readonly=True) as lmdb:
        lmdb.open_db(LMDB.QUERIES)

        try:
            MetaDatabase(lmdb, servers, create=False)  # check version and servers
        except NotImplementedError as exc:
            logging.critical(exc)
            sys.exit(1)

        dstream = repro.query_stream_from_disagreements(lmdb, report)
        try:
            repro.reproduce_queries(
                dstream, report, dnsreplies_factory, args.cfg['diff']['criteria'],
                args.cfg['diff']['target'], restart_scripts, nproc)
        finally:
            # make sure data is saved in case of interrupt
            report.export_json(datafile)


if __name__ == '__main__':
    main()
