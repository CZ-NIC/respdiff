#!/usr/bin/env bash
set -e

# Find Python scripts
FILES=$(find . \
	-name '*.py' -print)

python3 -m mypy --ignore-missing-imports ${FILES}
