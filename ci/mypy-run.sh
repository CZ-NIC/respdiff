#!/usr/bin/env bash
set -e

# Find Python scripts and skip directory cache_usage_benchmark
FILES=$(find . \
	-path './cache_usage_benchmark' -prune -o \
	-name '*.py' -print)

python3 -m mypy --ignore-missing-imports ${FILES}
