#!/usr/bin/env python3

import argparse
import logging
import sys
from typing import (  # noqa
    Any, AbstractSet, Iterable, Iterator, Mapping, Sequence, Tuple, TypeVar,
    Union)

from respdiff import cli, repro, sendrecv
from respdiff.database import DNSRepliesFactory, LMDB
from respdiff.dataformat import Diff, DiffReport, FieldLabel, ReproData, QID  # noqa


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description='attempt to reproduce original diffs from JSON report')
    cli.add_arg_envdir(parser)
    cli.add_arg_config(parser)
    cli.add_arg_datafile(parser)
    cli.add_arg_stats(parser)

    args = parser.parse_args()
    stats = args.stats

    if stats.queries is None:
        logging.critical("Statistics file contains no query information!")
        sys.exit(1)

    sendrecv.module_init(args)
    datafile = cli.get_datafile(args)
    report = DiffReport.from_json(datafile)
    restart_scripts = repro.get_restart_scripts(args.cfg)
    servers = args.cfg['servers']['names']
    dnsreplies_factory = DNSRepliesFactory(servers)
    nproc = args.cfg['sendrecv']['jobs']

    if report.reprodata is None:
        report.reprodata = ReproData()

    with LMDB(args.envdir, readonly=True) as lmdb:
        lmdb.open_db(LMDB.QUERIES)
        cli.check_metadb_servers_version(lmdb, servers)

        # gather all unverified queries to be reproduced
        qids = stats.queries.get_unseen_failures(report, verified=False)
        qids.update(stats.queries.get_fixed_queries(report, verified=False))

        try:
            while qids:  # as long as there are any unverified queries
                qstream = repro.query_stream_from_qids(lmdb, qids)
                repro.reproduce_queries(
                    qstream, report, dnsreplies_factory, args.cfg['diff']['criteria'],
                    args.cfg['diff']['target'], restart_scripts, nproc)
                qids = stats.queries.get_unseen_failures(report, verified=False)
                qids.update(stats.queries.get_fixed_queries(report, verified=False))
        finally:
            # make sure data is saved in case of interrupt
            report.export_json(datafile)

    # report
    qids = stats.queries.get_unseen_failures(report, verified=True)
    logging.info('NEW FAILING: %d', len(qids))
    qids = stats.queries.get_fixed_queries(report, verified=True)
    logging.info('NEW PASSING: %d', len(qids))


if __name__ == '__main__':
    main()
