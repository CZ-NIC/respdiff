#!/usr/bin/env python3

import argparse
import logging
import sys

from respdiff import cli
from respdiff.stats import SummaryStatistics


def _log_threshold(stats, label):
    percentile_rank = stats.get_percentile_rank(stats.threshold)
    logging.info("  %s: %4.2f percentile rank", label, percentile_rank)


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description="generate statistics file from reports"
    )
    cli.add_arg_report_filename(parser)
    cli.add_arg_stats_filename(parser)

    args = parser.parse_args()
    reports = cli.get_reports_from_filenames(args)

    try:
        sumstats = SummaryStatistics(reports)
    except ValueError as exc:
        logging.critical(exc)
        sys.exit(1)

    logging.info("Total sample size: %d", sumstats.sample_size)
    logging.info("Upper boundaries:")
    _log_threshold(sumstats.target_disagreements, "target_disagreements")
    _log_threshold(sumstats.upstream_unstable, "upstream_unstable")
    _log_threshold(sumstats.not_reproducible, "not_reproducible")
    for field_name, mismatch_stats in sumstats.fields.items():
        _log_threshold(mismatch_stats.total, field_name)

    sumstats.export_json(args.stats_filename)


if __name__ == "__main__":
    main()
