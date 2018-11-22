#!/usr/bin/env python3

import argparse
import logging
import sys
from typing import (  # noqa
    Any, Callable, Iterable, Iterator, ItemsView, List, Set, Sequence, Tuple,
    Union)

import dns.message
from respdiff import cli
from respdiff.database import LMDB
from respdiff.dataformat import DiffReport, Summary
from respdiff.dnsviz import DnsvizGrok
from respdiff.query import (
    convert_queries, get_printable_queries_format, get_query_iterator)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='create a summary report from gathered data stored in LMDB '
                    'and JSON datafile')
    cli.add_arg_envdir(parser)
    cli.add_arg_config(parser)
    cli.add_arg_datafile(parser)
    cli.add_arg_limit(parser)
    cli.add_arg_stats_filename(parser, default='')
    cli.add_arg_dnsviz(parser, default='')
    parser.add_argument('--without-dnsviz-errors', action='store_true',
                        help='omit domains that have any errors in DNSViz results')
    parser.add_argument('--without-diffrepro', action='store_true',
                        help='omit reproducibility data from summary')
    parser.add_argument('--without-ref-unstable', action='store_true',
                        help='omit unstable reference queries from summary')
    parser.add_argument('--without-ref-failing', action='store_true',
                        help='omit failing reference queries from summary')

    return parser.parse_args()


def check_args(args: argparse.Namespace, report: DiffReport):
    if (args.without_ref_unstable or args.without_ref_failing) \
            and not args.stats_filename:
        logging.critical("Statistics file must be provided as a reference.")
        sys.exit(1)
    if not report.total_answers:
        logging.error('No answers in DB!')
        sys.exit(1)
    if report.target_disagreements is None:
        logging.error('JSON report is missing diff data! Did you forget to run msgdiff?')
        sys.exit(1)


def main():
    cli.setup_logging()
    args = parse_args()
    datafile = cli.get_datafile(args)
    report = DiffReport.from_json(datafile)
    field_weights = args.cfg['report']['field_weights']

    check_args(args, report)

    ignore_qids = set()
    if args.without_ref_unstable or args.without_ref_failing:
        try:
            stats = cli.read_stats(args.stats_filename)
        except ValueError as exc:
            logging.critical(str(exc))
            sys.exit(1)
        if args.without_ref_unstable:
            ignore_qids.update(stats.queries.unstable)
        if args.without_ref_failing:
            ignore_qids.update(stats.queries.failing)

    report = DiffReport.from_json(datafile)
    report.summary = Summary.from_report(
        report, field_weights,
        without_diffrepro=args.without_diffrepro,
        ignore_qids=ignore_qids)

    # dnsviz filter: by domain -> need to iterate over disagreements to get QIDs
    if args.without_dnsviz_errors:
        try:
            dnsviz_grok = DnsvizGrok.from_json(args.dnsviz)
        except (FileNotFoundError, RuntimeError) as exc:
            logging.critical('Failed to load dnsviz data: %s', exc)
            sys.exit(1)

        error_domains = {domain for domain in dnsviz_grok.error_domains()}
        with LMDB(args.envdir, readonly=True) as lmdb:
            lmdb.open_db(LMDB.QUERIES)
            # match domain, add QID to ignore
            for qid, wire in get_query_iterator(lmdb, report.summary.keys()):
                msg = dns.message.from_wire(wire)
                if str(msg.question[0].name) in error_domains:
                    ignore_qids.add(qid)

        report.summary = Summary.from_report(
            report, field_weights,
            without_diffrepro=args.without_diffrepro,
            ignore_qids=ignore_qids)

    cli.print_global_stats(report)
    cli.print_differences_stats(report)

    if report.summary:  # when there are any differences to report
        field_counters = report.summary.get_field_counters()
        cli.print_fields_overview(field_counters, len(report.summary))
        for field in field_weights:
            if field in report.summary.field_labels:
                cli.print_field_mismatch_stats(
                    field, field_counters[field], len(report.summary))

        # query details
        with LMDB(args.envdir, readonly=True) as lmdb:
            lmdb.open_db(LMDB.QUERIES)

            for field in field_weights:
                if field in report.summary.field_labels:
                    for mismatch, qids in report.summary.get_field_mismatches(field):
                        queries = convert_queries(get_query_iterator(lmdb, qids))
                        cli.print_mismatch_queries(
                            field,
                            mismatch,
                            get_printable_queries_format(queries),
                            args.limit)

    report.export_json(datafile)


if __name__ == '__main__':
    main()
