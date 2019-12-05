#!/usr/bin/env python3

import argparse
from collections import Counter
import logging
import math
import sys

from respdiff import cli
from respdiff.database import LMDB
from respdiff.dataformat import DiffReport
from respdiff.query import (
    convert_queries, get_printable_queries_format, get_query_iterator)


ANSWERS_DIFFERENCE_THRESHOLD_WARNING = 0.05


def check_report_summary(report: DiffReport):
    if report.summary is None:
        logging.critical("report doesn't contain diff summary")
        sys.exit(1)


def check_usable_answers(report: DiffReport, ref_report: DiffReport):
    if report.summary is None or ref_report.summary is None:
        raise RuntimeError("Report doesn't contain necessary data!")
    answers_difference = math.fabs(
            report.summary.usable_answers - ref_report.summary.usable_answers
        ) / ref_report.summary.usable_answers
    if answers_difference >= ANSWERS_DIFFERENCE_THRESHOLD_WARNING:
        logging.warning('Number of usable answers changed by {:.1f} %!'.format(
            answers_difference * 100.0))


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(description='compare two diff summaries')
    cli.add_arg_config(parser)
    parser.add_argument('old_datafile', type=str, help='report to compare against')
    parser.add_argument('new_datafile', type=str, help='report to compare evaluate')
    cli.add_arg_envdir(parser)  # TODO remove when we no longer need to read queries from lmdb
    cli.add_arg_limit(parser)

    args = parser.parse_args()
    report = DiffReport.from_json(cli.get_datafile(args, key='new_datafile'))
    field_weights = args.cfg['report']['field_weights']
    ref_report = DiffReport.from_json(cli.get_datafile(args, key='old_datafile'))

    check_report_summary(report)
    check_report_summary(ref_report)
    check_usable_answers(report, ref_report)

    cli.print_global_stats(report, ref_report)
    cli.print_differences_stats(report, ref_report)

    if report.summary or ref_report.summary:  # when there are any differences to report
        field_counters = report.summary.get_field_counters()
        ref_field_counters = ref_report.summary.get_field_counters()

        # make sure "disappeared" fields show up as well
        for field in ref_field_counters:
            if field not in field_counters:
                field_counters[field] = Counter()

        cli.print_fields_overview(field_counters, len(report.summary), ref_field_counters)

        for field in field_weights:
            if field in field_counters:
                counter = field_counters[field]
                ref_counter = ref_field_counters.get(field, Counter())

                # make sure "disappeared" mismatches show up as well
                for mismatch in ref_counter:
                    if mismatch not in counter:
                        counter[mismatch] = 0

                cli.print_field_mismatch_stats(
                    field, counter, len(report.summary), ref_counter)

        # query details
        with LMDB(args.envdir, readonly=True) as lmdb:
            lmdb.open_db(LMDB.QUERIES)

            queries_all = convert_queries(
                get_query_iterator(lmdb, report.summary.keys()))
            ref_queries_all = convert_queries(
                get_query_iterator(lmdb, ref_report.summary.keys()))

            for field in field_weights:
                if field in field_counters:
                    # ensure "disappeared" mismatches are shown
                    field_mismatches = dict(report.summary.get_field_mismatches(field))
                    ref_field_mismatches = dict(ref_report.summary.get_field_mismatches(field))
                    mismatches = set(field_mismatches.keys())
                    mismatches.update(ref_field_mismatches.keys())

                    for mismatch in mismatches:
                        qids = field_mismatches.get(mismatch, set())
                        queries = convert_queries(get_query_iterator(lmdb, qids))
                        ref_queries = convert_queries(
                            get_query_iterator(lmdb, ref_field_mismatches.get(mismatch, set())))
                        cli.print_mismatch_queries(
                            field,
                            mismatch,
                            get_printable_queries_format(
                                queries,
                                queries_all,
                                ref_queries,
                                ref_queries_all),
                            args.limit)


if __name__ == '__main__':
    main()
