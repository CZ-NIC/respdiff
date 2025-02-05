#!/usr/bin/env python3

import argparse

from respdiff import cli, repro, sendrecv
from respdiff.database import DNSRepliesFactory, LMDB
from respdiff.dataformat import DiffReport, ReproData


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description="attempt to reproduce original diffs from JSON report"
    )
    cli.add_arg_envdir(parser)
    cli.add_arg_config(parser)
    cli.add_arg_datafile(parser)
    parser.add_argument(
        "--sequential",
        action="store_true",
        default=False,
        help="send one query at a time (slower, but more reliable)",
    )

    args = parser.parse_args()
    sendrecv.module_init(args)
    datafile = cli.get_datafile(args)
    report = DiffReport.from_json(datafile)
    restart_scripts = repro.get_restart_scripts(args.cfg)
    servers = args.cfg["servers"]["names"]
    dnsreplies_factory = DNSRepliesFactory(servers)

    if args.sequential:
        nproc = 1
    else:
        nproc = args.cfg["sendrecv"]["jobs"]

    if report.reprodata is None:
        report.reprodata = ReproData()

    with LMDB(args.envdir, readonly=True) as lmdb:
        lmdb.open_db(LMDB.QUERIES)
        cli.check_metadb_servers_version(lmdb, servers)

        dstream = repro.query_stream_from_disagreements(lmdb, report)
        try:
            repro.reproduce_queries(
                dstream,
                report,
                dnsreplies_factory,
                args.cfg["diff"]["criteria"],
                args.cfg["diff"]["target"],
                restart_scripts,
                nproc,
            )
        finally:
            # make sure data is saved in case of interrupt
            report.export_json(datafile)


if __name__ == "__main__":
    main()
