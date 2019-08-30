#!/usr/bin/env python3

import argparse
import logging
import statistics
import sys
from typing import Optional, Sequence

from respdiff import cli
from respdiff.stats import Stats, SummaryStatistics

WINDOW_SIZE = 5
INPUT_FILENAME = 'stats.json'
OUTPUT_FILENAME = 'stats_reduced.json'
MINIMAL_SAMPLE_SIZE = 0
JUMP_DETECTION_COEF = 1.2
THRESHOLD_COEF = 2


def last_jump_of_field(field: Optional[Stats], window_size: int = WINDOW_SIZE) -> int:
    if field is None:
        return 0
    seq = field.samples
    stdev = statistics.stdev(seq)
    mean: float = 0
    for i in range(len(seq)):
        if i > 0:
            local_mean = statistics.mean(seq[max(len(seq) - i - window_size, 0):-i])
            if (local_mean < mean - stdev * JUMP_DETECTION_COEF or
                    local_mean > mean + stdev * JUMP_DETECTION_COEF):
                return len(seq) - i
        mean = (mean*i + seq[-i - 1])/(i+1)
    return 0


def find_last_jump(stats: SummaryStatistics) -> int:
    jumps = []
    jumps.append(last_jump_of_field(stats.target_disagreements))
    jumps.append(last_jump_of_field(stats.upstream_unstable))
    jumps.append(last_jump_of_field(stats.not_reproducible))
    if stats.fields is not None:
        for field in stats.fields:
            jumps.append(last_jump_of_field(stats.fields[field].total))
    return max(jumps)


def find_threshold(seq: Sequence[float]) -> float:
    mean = statistics.mean(seq)
    stdev = statistics.stdev(seq, mean)
    return mean + THRESHOLD_COEF * stdev


def cut_field(field: Optional[Stats], jump: int) -> Optional[Stats]:
    if field is None:
        return None
    samples = field.samples[jump:]
    threshold = find_threshold(samples)
    return Stats(samples, threshold)


def cut_stats(stats: SummaryStatistics, last_jump: int) -> SummaryStatistics:
    stats.target_disagreements = cut_field(stats.target_disagreements, last_jump)
    stats.usable_answers = cut_field(stats.usable_answers, last_jump)
    stats.upstream_unstable = cut_field(stats.upstream_unstable, last_jump)
    stats.not_reproducible = cut_field(stats.not_reproducible, last_jump)
    if stats.fields is not None:
        for field in stats.fields:
            stats.fields[field].total = cut_field(stats.fields[field].total, last_jump)
            if stats.fields[field] is None:
                continue
            for mismatch in stats.fields[field]:
                stats.fields[field][mismatch] = cut_field(stats.fields[field][mismatch], last_jump)
    return stats


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(description='reduce stats to consistent values')
    parser.add_argument('-s', '--stats', type=cli.read_stats,
                        default=INPUT_FILENAME,
                        help='input statistics file (default: {})'.format(INPUT_FILENAME))
    parser.add_argument('-o', '--output', type=str,
                        default=OUTPUT_FILENAME,
                        help='output statistics file (default: {})'.format(OUTPUT_FILENAME))
    args = parser.parse_args()

    stats = args.stats

    last_jump = find_last_jump(stats)
    size = stats.sample_size - last_jump
    if size < MINIMAL_SAMPLE_SIZE:
        logging.critical("too few consistent values")
        sys.exit(1)

    stats = cut_stats(stats, last_jump)
    stats.sample_size = size

    stats.export_json(args.output)


if __name__ == '__main__':
    main()
