#!/usr/bin/env python3

import argparse
import logging
import sys
from typing import Sequence, Set

from respdiff import cli
from respdiff.database import LMDB
from respdiff.dataformat import DiffReport
from respdiff.query import get_query_iterator, qwire_to_qname, qwire_to_qname_qtype
from respdiff.typing import QID


def get_qids_to_export(
            args: argparse.Namespace,
            reports: Sequence[DiffReport]
        ) -> Set[QID]:
    qids = set()  # type: Set[QID]
    for report in reports:
        if args.failing:
            if report.summary is None:
                raise ValueError(
                    "Report {} is missing summary!".format(report.fileorigin))
            failing_qids = set(report.summary.keys())
            qids.update(failing_qids)
        if args.unstable:
            if report.other_disagreements is None:
                raise ValueError(
                    "Report {} is missing other disagreements!".format(report.fileorigin))
            unstable_qids = report.other_disagreements.queries
            qids.update(unstable_qids)
    return qids


def export_qids(qids: Set[QID], file=sys.stdout):
    for qid in qids:
        print(qid, file=file)


def export_qids_to_qname_qtype(qids: Set[QID], lmdb, file=sys.stdout):
    for _, qwire in get_query_iterator(lmdb, qids):
        print(qwire_to_qname_qtype(qwire), file=file)


def export_qids_to_qname(qids: Set[QID], lmdb, file=sys.stdout):
    domains = {qwire_to_qname(qwire) for _, qwire in get_query_iterator(lmdb, qids)}
    for domain in domains:
        print(domain, file=file)


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(description="export queries from reports' summaries")
    cli.add_arg_report_filename(parser, nargs='+')
    parser.add_argument('--envdir', type=str,
                        help="LMDB environment (required when output format isn't 'qid')")
    parser.add_argument('-f', '--format', type=str, choices=['text', 'qid', 'domain'],
                        default='domain', help="output data format")
    parser.add_argument('-o', '--output', type=str, help='output file')
    parser.add_argument('--failing', action='store_true', help="get target disagreements")
    parser.add_argument('--unstable', action='store_true', help="get upstream unstable")
    args = parser.parse_args()

    if args.format != 'qid' and not args.envdir:
        logging.critical("--envdir required when output format isn't 'qid'")
        sys.exit(1)

    if not args.failing and not args.unstable:
        logging.critical('No filter selected!')
        sys.exit(1)

    reports = cli.get_reports_from_filenames(args)
    if not reports:
        logging.critical('No reports found!')
        sys.exit(1)

    try:
        qids = get_qids_to_export(args, reports)
    except ValueError as exc:
        logging.critical(str(exc))
        sys.exit(1)

    with cli.smart_open(args.output) as fh:
        if args.format == 'qid':
            export_qids(qids, fh)
        else:
            with LMDB(args.envdir, readonly=True) as lmdb:
                lmdb.open_db(LMDB.QUERIES)

                if args.format == 'text':
                    export_qids_to_qname_qtype(qids, lmdb, fh)
                elif args.format == 'domain':
                    export_qids_to_qname(qids, lmdb, fh)


if __name__ == '__main__':
    main()
