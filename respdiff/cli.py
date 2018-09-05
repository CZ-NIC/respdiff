from argparse import ArgumentParser, Namespace
from collections import Counter
import logging
import os
import sys
from typing import Callable, Dict, Mapping, Optional, Sequence, Tuple, Union  # noqa

from tabulate import tabulate

from .cfg import read_cfg
from .database import MetaDatabase
from .dataformat import DiffReport, FieldLabel, InvalidFileFormat, Summary
from .match import DataMismatch
from .stats import SummaryStatistics

Number = Union[int, float]
StatsTuple = Tuple[int, Optional[float]]
ChangeStatsTuple = Tuple[int, Optional[float], Optional[int], Optional[float]]
ChangeStatsTupleStr = Tuple[int, Optional[float], Optional[str], Optional[float]]

LOGGING_LEVEL = logging.DEBUG
CONFIG_FILENAME = 'respdiff.cfg'
REPORT_FILENAME = 'report.json'
STATS_FILENAME = 'stats.json'
DEFAULT_PRINT_QUERY_LIMIT = 10


def read_stats(filename: str) -> SummaryStatistics:
    try:
        return SummaryStatistics.from_json(filename)
    except (FileNotFoundError, InvalidFileFormat) as exc:
        raise ValueError(exc)


def _handle_empty_report(exc: Exception, skip_empty: bool):
    if skip_empty:
        logging.debug('%s Omitting...', exc)
    else:
        logging.error(str(exc))
        raise ValueError(exc)


def read_report(filename: str, skip_empty: bool = False) -> Optional[DiffReport]:
    try:
        return DiffReport.from_json(filename)
    except (FileNotFoundError, InvalidFileFormat) as exc:
        _handle_empty_report(exc, skip_empty)
        return None


def load_summaries(
            reports: Sequence[DiffReport],
            skip_empty: bool = False
        ) -> Sequence[Summary]:

    summaries = []
    for report in reports:
        if report.summary is None:
            _handle_empty_report(
                ValueError('Empty diffsum in "{}"!'.format(report.fileorigin)),
                skip_empty)
        else:
            summaries.append(report.summary)
    return summaries


def setup_logging(level: int = LOGGING_LEVEL) -> None:
    logging.basicConfig(format='%(asctime)s %(levelname)8s  %(message)s', level=level)
    logger = logging.getLogger('matplotlib')
    # set WARNING for Matplotlib
    logger.setLevel(logging.WARNING)


def add_arg_config(parser: ArgumentParser) -> None:
    parser.add_argument('-c', '--config', type=read_cfg,
                        default=CONFIG_FILENAME, dest='cfg',
                        help='config file (default: {})'.format(CONFIG_FILENAME))


def add_arg_envdir(parser: ArgumentParser) -> None:
    parser.add_argument('envdir', type=str,
                        help='LMDB environment to read/write queries, answers and diffs')


def add_arg_datafile(parser: ArgumentParser) -> None:
    parser.add_argument('-d', '--datafile', type=str,
                        help='JSON report file (default: <envdir>/{})'.format(
                            REPORT_FILENAME))


def add_arg_limit(parser: ArgumentParser) -> None:
    parser.add_argument('-l', '--limit', type=int,
                        default=DEFAULT_PRINT_QUERY_LIMIT,
                        help='number of displayed mismatches in fields (default: {}; '
                             'use 0 to display all)'.format(DEFAULT_PRINT_QUERY_LIMIT))


def add_arg_stats(parser: ArgumentParser) -> None:
    parser.add_argument('-s', '--stats', type=read_stats,
                        default=STATS_FILENAME,
                        help='statistics file (default: {})'.format(STATS_FILENAME))


def add_arg_stats_filename(parser: ArgumentParser, default=STATS_FILENAME) -> None:
    parser.add_argument('-s', '--stats', type=str,
                        default=default, dest='stats_filename',
                        help='statistics file (default: {})'.format(default))


def add_arg_report(parser: ArgumentParser) -> None:
    parser.add_argument('report', type=read_report, nargs='*',
                        help='JSON report file(s)')


def add_arg_report_filename(parser: ArgumentParser) -> None:
    parser.add_argument('report', type=str, nargs='*',
                        help='JSON report file(s)')


def get_datafile(args: Namespace, key: str = 'datafile', check_exists: bool = True) -> str:
    datafile = getattr(args, key, None)
    if datafile is None:
        datafile = os.path.join(args.envdir, REPORT_FILENAME)

    if check_exists and not os.path.exists(datafile):
        logging.error("JSON report (%s) doesn't exist!", datafile)
        sys.exit(1)

    return datafile


def check_metadb_servers_version(lmdb, servers: Sequence[str]) -> None:
    try:
        MetaDatabase(lmdb, servers, create=False)  # check version and servers
    except NotImplementedError as exc:
        logging.critical(str(exc))
        sys.exit(1)


def format_stats_line(
            description: str,
            number: int,
            pct: float = None,
            diff: int = None,
            diff_pct: float = None,
            additional: str = None
        ) -> str:
    s = {}  # type: Dict[str, str]
    s['description'] = '{:21s}'.format(description)
    s['number'] = '{:8d}'.format(number)
    s['pct'] = '{:6.2f} %'.format(pct) if pct is not None else ' ' * 8
    s['additional'] = '{:30s}'.format(additional) if additional is not None else ' ' * 30
    s['diff'] = '{:+6d}'.format(diff) if diff is not None else ' ' * 6
    s['diff_pct'] = '{:+7.2f} %'.format(diff_pct) if diff_pct is not None else ' ' * 9

    return '{description}   {number}  {pct} {additional} {diff} {diff_pct}'.format(**s)


def get_stats_data(
            n: int,
            total: int = None,
            ref_n: int = None,
        ) -> ChangeStatsTuple:
    """
    Return absolute and relative data statistics

    Optionally, the data is compared with a reference.
    """
    def percentage(
                dividend: Number,
                divisor: Optional[Number]
            ) -> Optional[float]:
        """Return dividend/divisor value in %"""
        if divisor is None:
            return None
        if divisor == 0:
            if dividend > 0:
                return float('+inf')
            if dividend < 0:
                return float('-inf')
            return float('nan')
        return dividend * 100.0 / divisor

    pct = percentage(n, total)
    diff = None
    diff_pct = None

    if ref_n is not None:
        diff = n - ref_n
        diff_pct = percentage(diff, ref_n)

    return n, pct, diff, diff_pct


def get_table_stats_row(
            count: int,
            total: int,
            ref_count: Optional[int] = None
        ) -> Union[StatsTuple, ChangeStatsTupleStr]:
    n, pct, diff, diff_pct = get_stats_data(  # type: ignore
        count,
        total,
        ref_count)
    if ref_count is None:
        return n, pct
    s_diff = '{:+d}'.format(diff) if diff is not None else None
    return n, pct, s_diff, diff_pct


def print_fields_overview(
            field_counters: Mapping[FieldLabel, Counter],
            n_disagreements: int,
            ref_field_counters: Optional[Mapping[FieldLabel, Counter]] = None,
        ) -> None:
    rows = []

    def get_field_count(counter: Counter) -> int:
        field_count = 0
        for count in counter.values():
            field_count += count
        return field_count

    ref_field_count = None
    for field, counter in field_counters.items():
        field_count = get_field_count(counter)
        if ref_field_counters is not None:
            ref_counter = ref_field_counters.get(field, Counter())
            ref_field_count = get_field_count(ref_counter)
        rows.append((field, *get_table_stats_row(
            field_count, n_disagreements, ref_field_count)))

    headers = ['Field', 'Count', '% of mismatches']
    if ref_field_counters is not None:
        headers.extend(['Change', 'Change (%)'])

    print('== Target Disagreements')
    print(tabulate(
        sorted(rows, key=lambda data: data[1], reverse=True),
        headers,
        tablefmt='simple',
        floatfmt=('s', 'd', '.2f', 's', '+.2f')))
    print('')


def print_field_mismatch_stats(
            field: FieldLabel,
            counter: Counter,
            n_disagreements: int,
            ref_counter: Counter = None
        ) -> None:
    rows = []

    ref_count = None
    for mismatch, count in counter.items():
        if ref_counter is not None:
            ref_count = ref_counter[mismatch]
        rows.append((
            DataMismatch.format_value(mismatch.exp_val),
            DataMismatch.format_value(mismatch.got_val),
            *get_table_stats_row(
                count, n_disagreements, ref_count)))

    headers = ['Expected', 'Got', 'Count', '% of mimatches']
    if ref_counter is not None:
        headers.extend(['Change', 'Change (%)'])

    print('== Field "{}" mismatch statistics'.format(field))
    print(tabulate(
        sorted(rows, key=lambda data: data[2], reverse=True),
        headers,
        tablefmt='simple',
        floatfmt=('s', 's', 'd', '.2f', 's', '+.2f')))
    print('')


def print_global_stats(report: DiffReport, reference: DiffReport = None) -> None:
    ref_duration = getattr(reference, 'duration', None)
    ref_total_answers = getattr(reference, 'total_answers', None)
    ref_total_queries = getattr(reference, 'total_queries', None)

    if (report.duration is None
            or report.total_answers is None
            or report.total_queries is None):
        raise RuntimeError("Report doesn't containt necassary data!")

    print('== Global statistics')
    print(format_stats_line('duration', *get_stats_data(
        report.duration, ref_n=ref_duration),
        additional='seconds'))
    print(format_stats_line('queries', *get_stats_data(
        report.total_queries, ref_n=ref_total_queries)))
    print(format_stats_line('answers', *get_stats_data(
        report.total_answers, report.total_queries,
        ref_total_answers),
        additional='of queries'))
    print('')


def print_differences_stats(report: DiffReport, reference: DiffReport = None) -> None:
    ref_summary = getattr(reference, 'summary', None)
    ref_upstream_unstable = getattr(ref_summary, 'upstream_unstable', None)
    ref_not_reproducible = getattr(ref_summary, 'not_reproducible', None)
    ref_target_disagrees = len(ref_summary) if ref_summary is not None else None

    if report.summary is None:
        raise RuntimeError("Report doesn't containt necassary data!")

    print('== Differences statistics')
    print(format_stats_line('upstream unstable', *get_stats_data(
        report.summary.upstream_unstable, report.total_answers,
        ref_upstream_unstable),
        additional='of answers (ignoring)'))
    print(format_stats_line('not 100% reproducible', *get_stats_data(
        report.summary.not_reproducible, report.total_answers,
        ref_not_reproducible),
        additional='of answers (ignoring)'))
    print(format_stats_line('target disagrees', *get_stats_data(
        len(report.summary), report.summary.usable_answers,
        ref_target_disagrees),
        additional='of not ignored answers'))
    print('')


def print_mismatch_queries(
            field: FieldLabel,
            mismatch: DataMismatch,
            queries: Sequence[Tuple[str, int, str]],
            limit: Optional[int] = DEFAULT_PRINT_QUERY_LIMIT
        ) -> None:
    if limit == 0:
        limit = None

    def sort_key(data: Tuple[str, int, str]) -> Tuple[int, int]:
        order = ['+', ' ', '-']
        try:
            return order.index(data[0]), -data[1]
        except ValueError:
            return len(order), -data[1]

    def format_line(diff: str, count: str, query: str) -> str:
        return "{:1s} {:>7s}  {:s}".format(diff, count, query)

    to_print = sorted(queries, key=sort_key)
    to_print = to_print[:limit]

    print('== Field "{}", mismatch "{}" query details'.format(field, mismatch))
    print(format_line('', 'Count', 'Query'))
    for diff, count, query in to_print:
        print(format_line(diff, str(count), query))

    if limit is not None and limit < len(queries):
        print(format_line(
            'x',
            str(len(queries) - limit),
            'queries omitted'))
    print('')
