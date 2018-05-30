#!/usr/bin/env python3

import argparse
from collections import Counter
import logging
import sys
from typing import (  # noqa
    Any, Callable, Iterable, Iterator, ItemsView, List, Set, Sequence, Tuple,
    Union)

import dns.message
import dns.rdatatype

from respdiff import cli
from respdiff.dataformat import DiffReport, Summary, QID
from respdiff.dbhelper import LMDB, qid2key, WireFormat


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


def qwire_to_qname_qtype(qwire: WireFormat) -> str:
    """Get text representation of DNS wire format query"""
    qmsg = dns.message.from_wire(qwire)
    return '{} {}'.format(
        qmsg.question[0].name,
        dns.rdatatype.to_text(qmsg.question[0].rdtype))


def convert_queries(
            query_iterator: Iterator[Tuple[QID, WireFormat]],
            qwire_to_text_func: Callable[[WireFormat], str] = qwire_to_qname_qtype
        ) -> Counter:
    qcounter = Counter()  # type: Counter
    for _, qwire in query_iterator:
        text = qwire_to_text_func(qwire)
        qcounter[text] += 1
    return qcounter


def get_printable_queries_format(
            queries_mismatch: Counter,
            queries_all: Counter = None,  # all queries (needed for comparison with ref)
            ref_queries_mismatch: Counter = None,  # ref queries for the same mismatch
            ref_queries_all: Counter = None  # ref queries from all mismatches
        ) -> Sequence[Tuple[str, int, str]]:
    def get_query_diff(query: str) -> str:
        if (ref_queries_mismatch is None
                or ref_queries_all is None
                or queries_all is None):
            return ' '  # no reference to compare to
        if query in queries_mismatch and query not in ref_queries_all:
            return '+'  # previously unseen query has appeared
        if query in ref_queries_mismatch and query not in queries_all:
            return '-'  # query no longer appears in any mismatch category
        return ' '  # no change, or query has moved to a different mismatch category

    query_set = set(queries_mismatch.keys())
    if ref_queries_mismatch is not None:
        assert ref_queries_all is not None
        assert queries_all is not None
        # ref_mismach has to be include to be able to display '-' queries
        query_set.update(ref_queries_mismatch.keys())

    queries = []
    for query in query_set:
        diff = get_query_diff(query)
        count = queries_mismatch[query]
        if diff == ' ' and count == 0:
            continue  # omit queries that just moved between categories
        if diff == '-':
            assert ref_queries_mismatch is not None
            count = ref_queries_mismatch[query]  # show how many cases were removed
        queries.append((diff, count, query))
    return queries


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
