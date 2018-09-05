#!/usr/bin/env python3

import argparse
import logging
import sys

from respdiff import cli, repro, sendrecv
from respdiff.database import DNSRepliesFactory, LMDB
from respdiff.dataformat import DiffReport, ReproData
from respdiff.qstats import MAX_REPRO_ATTEMPTS


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

        try:
            for i in range(MAX_REPRO_ATTEMPTS):
                logging.info('Repro Attempt %d (max %d)', i, MAX_REPRO_ATTEMPTS)
                # gather all unverified queries to be reproduced
                qids = stats.queries.get_unseen_failures(report, verified=False)
                qids.update(stats.queries.get_fixed_queries(report, verified=False))

                if not qids:
                    break

                qstream = repro.query_stream_from_qids(lmdb, qids)
                repro.reproduce_queries(
                    qstream, report, dnsreplies_factory, args.cfg['diff']['criteria'],
                    args.cfg['diff']['target'], restart_scripts, nproc)
        finally:
            # make sure data is saved in case of interrupt
            report.export_json(datafile)


if __name__ == '__main__':
    main()
