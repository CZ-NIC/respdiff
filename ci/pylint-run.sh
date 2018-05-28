#!/usr/bin/env bash
set -e

# Find Python modules and standalone Python scripts, skip directory
# cache_usage_benchmark
FILES=$(find . \
	-type d -exec test -e '{}/__init__.py' \; -print -prune -o \
	-path './cache_usage_benchmark' -prune -o \
	-name '*.py' -print)

PYTHONPATH=response_differences python3 -m pylint -j 2 --rcfile pylintrc ${FILES}
