#!/usr/bin/env bash
WORKING_DIR="$(pwd)"
RET_CODE=0
IFS=$'\n'
for FILE in $(find . -name '*.py' | sort | grep -v '\./cache_usage_benchmark')
do
  cd "${WORKING_DIR}"
  cd "`dirname "${FILE}"`"
  echo "${FILE}"
  python3 -m pylint -E "`basename \"${FILE}\"`" 2>/dev/null || RET_CODE=1
done
cd "${WORKING_DIR}"
exit $RET_CODE