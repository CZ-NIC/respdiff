#!/usr/bin/env python3

import argparse
import base64
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
    if args.qidlist:
        with open(args.qidlist) as qidlist_file:
            qids.update(int(qid.strip())
                        for qid in qidlist_file
                        if qid.strip())
    return qids


def export_qids(qids: Set[QID], file=sys.stdout):
    for qid in qids:
        print(qid, file=file)


def export_qids_to_qname_qtype(qids: Set[QID], lmdb, file=sys.stdout):
    for qid, qwire in get_query_iterator(lmdb, qids):
        try:
            query = qwire_to_qname_qtype(qwire)
        except ValueError as exc:
            logging.debug('Omitting QID %d from export: %s', qid, exc)
        else:
            print(query, file=file)


def export_qids_to_qname(qids: Set[QID], lmdb, file=sys.stdout):
    domains = set()  # type: Set[str]
    for qid, qwire in get_query_iterator(lmdb, qids):
        try:
            qname = qwire_to_qname(qwire)
        except ValueError as exc:
            logging.debug('Omitting QID %d from export: %s', qid, exc)
        else:
            if qname not in domains:
                print(qname, file=file)
                domains.add(qname)


def export_qids_to_base64url(qids: Set[QID], lmdb, file=sys.stdout):
    wires = set()  # type: Set[bytes]
    for _, qwire in get_query_iterator(lmdb, qids):
        if qwire not in wires:
            print(base64.urlsafe_b64encode(qwire).decode('ascii'), file=file)
            wires.add(qwire)


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(description="export queries from reports' summaries")
    cli.add_arg_report_filename(parser, nargs='+')
    parser.add_argument('--envdir', type=str,
                        help="LMDB environment (required when output format isn't 'qid')")
    parser.add_argument('-f', '--format', type=str, choices=['query', 'qid', 'domain', 'base64url'],
                        default='domain', help="output data format")
    parser.add_argument('-o', '--output', type=str, help='output file')
    parser.add_argument('--failing', action='store_true', help="get target disagreements")
    parser.add_argument('--unstable', action='store_true', help="get upstream unstable")
    parser.add_argument('--qidlist', type=str, help='path to file with list of QIDs to export')

    args = parser.parse_args()

    if args.format != 'qid' and not args.envdir:
        logging.critical("--envdir required when output format isn't 'qid'")
        sys.exit(1)

    if not args.failing and not args.unstable and not args.qidlist:
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

                if args.format == 'query':
                    export_qids_to_qname_qtype(qids, lmdb, fh)
                elif args.format == 'domain':
                    export_qids_to_qname(qids, lmdb, fh)
                elif args.format == 'base64url':
                    export_qids_to_base64url(qids, lmdb, fh)
                else:
                    raise ValueError('unsupported output format')


if __name__ == '__main__':
    main()
