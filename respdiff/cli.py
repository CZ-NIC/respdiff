from argparse import ArgumentParser, Namespace
import logging
import math
import os
import sys
from typing import Dict, Mapping, Optional, Tuple, Union  # noqa

from tabulate import tabulate

import cfg
from dataformat import DataMismatch, DiffReport, FieldCounter, FieldLabel


Number = Union[int, float]

LOGGING_LEVEL = logging.DEBUG
CONFIG_FILENAME = 'respdiff.cfg'
REPORT_FILENAME = 'report.json'


def setup_logging(level: int = LOGGING_LEVEL) -> None:
    logging.basicConfig(format='%(asctime)s %(levelname)8s  %(message)s', level=level)


def add_arg_config(parser: ArgumentParser) -> None:
    parser.add_argument('-c', '--config', type=cfg.read_cfg,
                        default=CONFIG_FILENAME, dest='cfg',
                        help='config file (default: {})'.format(CONFIG_FILENAME))


def add_arg_envdir(parser: ArgumentParser) -> None:
    parser.add_argument('envdir', type=str,
                        help='LMDB environment to read/write queries, answers and diffs')


def add_arg_datafile(parser: ArgumentParser) -> None:
    parser.add_argument('-d', '--datafile', type=str,
                        help='JSON report file (default: <envdir>/{})'.format(
                            REPORT_FILENAME))


def get_datafile(args: Namespace, check_exists: bool = True, key: str = 'datafile') -> str:
    datafile = getattr(args, key, None)
    if datafile is None:
        datafile = os.path.join(args.envdir, REPORT_FILENAME)

    if check_exists and not os.path.exists(datafile):
        logging.error("JSON report (%s) doesn't exist!", datafile)
        sys.exit(1)

    return datafile


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
    s['diff_pct'] = '{:+7.2f}'.format(diff_pct) if diff_pct is not None else ' ' * 7

    return '{description}   {number}  {pct} {additional} {diff} {diff_pct}'.format(**s)


def get_stats_data(
            n: int,
            total: int = None,
            ref_n: int = None,
        ) -> Tuple[int, float, Optional[int], Optional[float]]:
    """
    Return absolute and relative data statistics

    Optionally, the data is compared with a reference.
    """
    def percentage(
                dividend: Union[int, float],
                divisor: Union[int, float]
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


def print_fields_overview(
            field_counters: Mapping[FieldLabel, FieldCounter]
        ) -> None:
    columns = sorted([
            (field, counter.count, counter.percent)
            for field, counter in field_counters.items()],
        key=lambda data: data[1],
        reverse=True)
    print('== Target Disagreements')
    print(tabulate(
        columns,
        ['Field', 'Count', '% of mismatches'],
        tablefmt='simple',
        floatfmt='.2f'))
    print('')


def print_field_mismatch_stats(
            field: FieldLabel,
            field_counter: FieldCounter
        ) -> None:
    columns = sorted([(
                DataMismatch.format_value(mismatch.exp_val),
                DataMismatch.format_value(mismatch.got_val),
                counter.count, counter.percent)
            for mismatch, counter in field_counter.items()],
        key=lambda data: data[2],
        reverse=True)
    print('== Field "{}" mismatch statistics'.format(field))
    print(tabulate(
        columns,
        ['Expected', 'Got', 'Count', '% of mismatches'],
        tablefmt='simple',
        floatfmt='.2f'))
    print('')


def print_global_stats(report: DiffReport, reference: DiffReport = None) -> None:
    ref_duration = getattr(reference, 'duration', None)
    ref_total_answers = getattr(reference, 'total_answers', None)
    ref_total_queries = getattr(reference, 'total_queries', None)

    print('== Global statistics')
    print(format_stats_line('duration', *get_stats_data(
        report.duration, ref_n=ref_duration),
        additional='seconds'))
    print(format_stats_line('queries', *get_stats_data(
        report.total_queries, ref_n=ref_total_queries)))
    print(format_stats_line('answers', *get_stats_data(
        report.total_answers, report.total_queries,
        ref_total_answers, ref_total_queries)))
    print('')


def print_differences_stats(report: DiffReport, reference: DiffReport = None) -> None:
    ref_upstream_unstable = getattr(reference, 'upstream_unstable', None)
    ref_total_answers = getattr(reference, 'total_answers', None)
    ref_not_reproducible = getattr(reference, 'not_reproducible', None)
    ref_summary = getattr(reference, 'summary', None)
    ref_target_disagrees = len(ref_summary) if ref_summary is not None else None
    ref_usable_answers = getattr(reference, 'usable_answers', None)

    print('== Differences statistics')
    print(format_stats_line('upstream unstable', *get_stats_data(
        report.summary.upstream_unstable, report.total_answers,
        ref_upstream_unstable, ref_total_answers),
        additional='of answers (ignoring)'))
    print(format_stats_line('not 100% reproducible', *get_stats_data(
        report.summary.not_reproducible, report.total_answers,
        ref_not_reproducible, ref_total_answers),
        additional='of answers (ignoring)'))
    print(format_stats_line('target disagrees', *get_stats_data(
        len(report.summary), report.summary.usable_answers,
        ref_target_disagrees, ref_usable_answers),
        additional='of not ignored answers'))
    print('')
