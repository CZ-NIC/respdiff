#!/usr/bin/env bash
WORKING_DIR=$(pwd);
RET_CODE=0;
for DIR in $(find . -type d | grep -v '\./\.' | grep -v '\./cache_usage_benchmark');
do
  cd ${WORKING_DIR}
  cd ${DIR}
  find . -maxdepth 1 -type f  | grep  -q .py$ && \
  printf "\n*Working directory: ${DIR}\n" && \
  (python3 -m pylint -E `find . -maxdepth 1 -type f | grep .py$` && echo "No PYLINT errors detected in this directory" || RET_CODE=1)
done
cd ${WORKING_DIR}
exit $RET_CODE