#!/usr/bin/env python3

import argparse
import logging
import os
import sys
from typing import Sequence

from respdiff import cli
from respdiff.dataformat import DiffReport, InvalidFileFormat, Summary
from respdiff.stats import SummaryStatistics


def load_summaries(datafiles: Sequence[str]) -> Sequence[Summary]:
    summaries = []
    for datafile in datafiles:
        if not os.path.exists(datafile):
            logging.warning('Report "%s" not found! Omitting from statistics.',
                            datafile)
            continue
        try:
            report = DiffReport.from_json(datafile)
        except InvalidFileFormat:
            logging.warning('Failed to parse report "%s"! Omitting from statistics.',
                            datafile)
            continue
        if report.summary is None:
            logging.warning('Empty diffsum in "%s"! Omitting from statistics.', datafile)
            continue
        summaries.append(report.summary)

    logging.info('Total sample size: %d', len(summaries))
    if not summaries:
        logging.critical('No reports found!')
        sys.exit(1)
    return summaries


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(description='generate statistics file from reports')
    parser.add_argument('datafiles', type=str, nargs='+',
                        help='reports to calculate stats from')
    parser.add_argument('-o', '--output', type=str, default='stats.json',
                        help='statistics output file (default: stats.json)')

    args = parser.parse_args()
    summaries = load_summaries(args.datafiles)
    stats = SummaryStatistics(summaries)
    stats.export_json(args.output)


if __name__ == '__main__':
    main()
