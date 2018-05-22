#!/usr/bin/env python3

import argparse
import collections
import logging
import sys
from typing import (  # noqa
    Any, Callable, Iterable, Iterator, ItemsView, List, Optional, Set, Tuple,
    Union)

import dns.message
import dns.rdatatype
from tabulate import tabulate

import cli
from dbhelper import LMDB, qid2key, WireFormat
from dataformat import DataMismatch, DiffReport, FieldLabel, Summary, QID


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


def print_fields_overview(summary: Summary) -> None:
    fields = []
    for field in summary.field_labels:
        mismatch_count = 0
        for _, qids in summary.get_field_mismatches(field):
            mismatch_count += len(qids)
        fields.append([field, mismatch_count, mismatch_count * 100.0 / len(summary)])
    fields.sort(key=lambda data: data[1], reverse=True)

    print('== Target Disagreements')
    print(tabulate(
        fields,
        ['Field', 'Count', '% of mismatches'],
        tablefmt='psql',
        floatfmt='.2f'))
    print('')


def print_field_mismatch_stats(
            field: FieldLabel,
            mismatches: ItemsView[DataMismatch, Set[QID]],
            total_mismatches: int
        ) -> None:
    fields = []
    for mismatch, qids in mismatches:
        fields.append([
            mismatch.format_value(mismatch.exp_val),
            mismatch.format_value(mismatch.got_val),
            len(qids),
            len(qids) * 100. / total_mismatches])
    fields.sort(key=lambda data: data[2], reverse=True)

    print('== Field "{}" mismatch statistics'.format(field))
    print(tabulate(
        fields,
        ['Expected', 'Got', 'Count', '% of mismatches'],
        tablefmt='psql',
        floatfmt='.2f'))
    print('')


def qwire_to_qname_qtype(qwire: WireFormat) -> str:
    """Get text representation of DNS wire format query"""
    qmsg = dns.message.from_wire(qwire)
    return '{} {}'.format(
        qmsg.question[0].name,
        dns.rdatatype.to_text(qmsg.question[0].rdtype))


def print_mismatch_queries(
            field: FieldLabel,
            mismatch: DataMismatch,
            queries: Iterator[Tuple[QID, WireFormat]],
            limit: Optional[int] = DEFAULT_LIMIT,
            qwire_to_text_func: Callable[[WireFormat], str] = qwire_to_qname_qtype
        ) -> None:
    occurences = collections.Counter()  # type: collections.Counter
    for _, qwire in queries:
        text = qwire_to_text_func(qwire)
        occurences[text] += 1
    if limit == 0:
        limit = None
    to_print = [(count, text) for text, count in occurences.most_common(limit)]

    print('== Field "{}", mismatch "{}" query details'.format(field, mismatch))
    print(tabulate(
        to_print,
        ['Count', 'Query'],
        tablefmt='plain'))
    if limit is not None and limit < len(occurences):
        print('    ...  omitting {} queries'.format(len(occurences) - limit))
    print('')


def get_query_iterator(
            lmdb,
            qids: Iterable[QID]
        ) -> Iterator[Tuple[QID, WireFormat]]:
    qdb = lmdb.get_db(LMDB.QUERIES)
    with lmdb.env.begin(qdb) as txn:
        for qid in qids:
            key = qid2key(qid)
            qwire = txn.get(key)
            yield qid, qwire


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description='create a summary report from gathered data stored in LMDB '
                    'and JSON datafile')
    cli.add_arg_envdir(parser)
    cli.add_arg_config(parser)
    cli.add_arg_datafile(parser)
    parser.add_argument('-l', '--limit', type=int, default=DEFAULT_LIMIT,
                        help='number of displayed mismatches in fields (default: {}; '
                             'use 0 to display all)'.format(DEFAULT_LIMIT))

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

    print_global_stats(report)
    print_differences_stats(report.summary, report.total_answers)

    if report.summary:
        print_fields_overview(report.summary)
        for field in field_weights:
            if field in report.summary.field_labels:
                print_field_mismatch_stats(
                    field,
                    report.summary.get_field_mismatches(field),
                    len(report.summary))

        # query details
        with LMDB(args.envdir, readonly=True) as lmdb:
            lmdb.open_db(LMDB.QUERIES)
            for field in field_weights:
                if field in report.summary.field_labels:
                    for mismatch, qids in report.summary.get_field_mismatches(field):
                        queries = get_query_iterator(lmdb, qids)
                        print_mismatch_queries(field, mismatch, queries, args.limit)

    report.export_json(datafile)


if __name__ == '__main__':
    main()
