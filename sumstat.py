#!/usr/bin/env python3

import argparse
import logging
import sys

from respdiff import cli
from respdiff.stats import SummaryStatistics


def _log_upper_boundary(stats, label):
    percentile_rank = stats.get_percentile_rank(stats.upper_boundary)
    logging.info('  %s: %4.2f percentile rank', label, percentile_rank)


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

    sumstats = SummaryStatistics(summaries)

    logging.info('Total sample size: %d', len(summaries))
    logging.info('Upper boundaries:')
    _log_upper_boundary(sumstats.target_disagreements, 'target_disagreements')
    _log_upper_boundary(sumstats.upstream_unstable, 'upstream_unstable')
    _log_upper_boundary(sumstats.not_reproducible, 'not_reproducible')
    for field_name, mismatch_stats in sumstats.fields.items():
        _log_upper_boundary(mismatch_stats.total, field_name)

    sumstats.export_json(args.stats_filename)


if __name__ == '__main__':
    main()
