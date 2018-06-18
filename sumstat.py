#!/usr/bin/env python3

import argparse
import logging
import sys

from respdiff import cli
from respdiff.stats import SummaryStatistics


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(description='generate statistics file from reports')
    cli.add_arg_report(parser)
    cli.add_arg_stats_filename(parser)

    args = parser.parse_args()
    reports = [report for report in args.report if report is not None]
    summaries = cli.load_summaries(reports)

    if not summaries:
        logging.critical('No summaries found in reports!')
        sys.exit(1)

    stats = SummaryStatistics(summaries)

    logging.info('Total sample size: %d', len(summaries))
    stats.export_json(args.stats_filename)  # TODO bak


if __name__ == '__main__':
    main()
