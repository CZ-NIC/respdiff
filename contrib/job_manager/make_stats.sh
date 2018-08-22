#!/bin/bash
set -o nounset

RESPDIFF_SRC=/var/opt/respdiff

COMMIT_DIR=${1:-.}
pushd ${COMMIT_DIR}

ID=$(basename $(readlink -f ${PWD}))

for DIR in *; do
    if [ -d "${DIR}" ]; then
        STATFILE=${ID}_${DIR}_stats.json
        ${RESPDIFF_SRC}/sumstat.py -s "${STATFILE}" ${DIR}/*_report.json
        ${RESPDIFF_SRC}/statcmp.py -s "${STATFILE}" -c "${DIR}/respdiff.cfg" -l "${ID}_${DIR}"

        STATFILE=${ID}_${DIR}_stats.diffrepro.json
        ${RESPDIFF_SRC}/sumstat.py -s "${STATFILE}" ${DIR}/*_report.diffrepro.json
        ${RESPDIFF_SRC}/statcmp.py -s "${STATFILE}" -c "${DIR}/respdiff.cfg" -l "${ID}_${DIR}.diffrepro"
    fi
done

popd
