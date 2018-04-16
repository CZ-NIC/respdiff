from argparse import ArgumentParser, Namespace
import logging
import os
import sys
from typing import Mapping

from tabulate import tabulate

import cfg
from dataformat import DataMismatch, FieldCounter, FieldLabel


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
        tablefmt='psql',
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
        tablefmt='psql',
        floatfmt='.2f'))
    print('')
