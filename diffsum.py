#!/usr/bin/env python3

import argparse
import logging
import sys
from typing import (  # noqa
    Any, Callable, Iterable, Iterator, ItemsView, List, Set, Sequence, Tuple,
    Union)

from respdiff import cli
from respdiff.dataformat import DiffReport, Summary
from respdiff.dbhelper import LMDB
from respdiff.query import (
    convert_queries, get_printable_queries_format, get_query_iterator)


DEFAULT_LIMIT = 10
GLOBAL_STATS_FORMAT = '{:21s}   {:>8}'
GLOBAL_STATS_PCT_FORMAT = '{:21s}   {:8d}   {:5.2f} % {:s}'


def print_global_stats(report: DiffReport) -> None:
    if report.total_answers is None or report.total_queries is None:
        raise RuntimeError("Report doesn't contain sufficient data to print statistics!")
    print('== Global statistics')
    if report.duration is not None:
        print(GLOBAL_STATS_FORMAT.format('duration', '{:d} s'.format(report.duration)))
    print(GLOBAL_STATS_FORMAT.format('queries', report.total_queries))
    print(GLOBAL_STATS_PCT_FORMAT.format(
        'answers', report.total_answers,
        report.total_answers * 100.0 / report.total_queries, 'of queries'))
    print('')


def print_differences_stats(summary: Summary, total_answers: int) -> None:
    print('== Differences statistics')
    print(GLOBAL_STATS_PCT_FORMAT.format(
        'upstream unstable', summary.upstream_unstable,
        summary.upstream_unstable * 100.0 / total_answers, 'of answers (ignoring)'))
    if summary.not_reproducible:
        print(GLOBAL_STATS_PCT_FORMAT.format(
            'not 100% reproducible', summary.not_reproducible,
            summary.not_reproducible * 100.0 / total_answers, 'of answers (ignoring)'))
    print(GLOBAL_STATS_PCT_FORMAT.format(
        'target disagrees', len(summary),
        len(summary) * 100. / summary.usable_answers,
        'of not ignored answers'))
    print('')


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description='create a summary report from gathered data stored in LMDB '
                    'and JSON datafile')
    cli.add_arg_envdir(parser)
    cli.add_arg_config(parser)
    cli.add_arg_datafile(parser)
    cli.add_arg_limit(parser)

    args = parser.parse_args()
    datafile = cli.get_datafile(args)
    report = DiffReport.from_json(datafile)
    field_weights = args.cfg['report']['field_weights']

    if not report.total_answers:
        logging.error('No answers in DB!')
        sys.exit(1)
    if report.target_disagreements is None:
        logging.error('JSON report is missing diff data! Did you forget to run msgdiff?')
        sys.exit(1)

    report = DiffReport.from_json(datafile)
    report.summary = Summary.from_report(report, field_weights)

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
