#!/usr/bin/env python3

import argparse
import logging
import statistics
import sys
from typing import Optional

from respdiff import cli
from respdiff.stats import Stats, SummaryStatistics

DEFAULT_COEF = 2


def belongs_to_distribution(ref: Optional[Stats], new: Optional[Stats], coef: float) -> bool:
    if ref is None or new is None:
        return False
    median = statistics.median(new.samples)
    if median > statistics.mean(ref.samples) + coef * statistics.stdev(ref.samples):
        return False
    if median < statistics.mean(ref.samples) - coef * statistics.stdev(ref.samples):
        return False
    return True


def belongs_to_all(ref: SummaryStatistics, new: SummaryStatistics, coef: float) -> bool:
    if not belongs_to_distribution(ref.target_disagreements, new.target_disagreements, coef):
        return False
    if not belongs_to_distribution(ref.upstream_unstable, new.upstream_unstable, coef):
        return False
    if not belongs_to_distribution(ref.not_reproducible, new.not_reproducible, coef):
        return False
    if ref.fields is not None and new.fields is not None:
        for field in ref.fields:
            if not belongs_to_distribution(ref.fields[field].total, new.fields[field].total, coef):
                return False
    return True


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(description='Check if new samples belong to reference '
                                                 'distribution. Ends with exitcode 0 if belong, '
                                                 '1 if not,')
    parser.add_argument('-r', '--reference', type=cli.read_stats,
                        help='json statistics file with reference data')
    cli.add_arg_report_filename(parser)
    parser.add_argument('-c', '--coef', type=float,
                        default=DEFAULT_COEF,
                        help=('coeficient for comparation (new belongs to refference if '
                              'its median is closer than COEF * standart deviation of reference '
                              'from reference mean) (default: {})'.format(DEFAULT_COEF)))
    args = parser.parse_args()
    reports = cli.get_reports_from_filenames(args)

    try:
        newstats = SummaryStatistics(reports)
    except ValueError as exc:
        logging.critical(exc)
        sys.exit(2)

    if not belongs_to_all(args.reference, newstats, args.coef):
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
