#!/bin/bash

set -o nounset

COMMIT_DIR=${1:-.}
REF_COMMIT_DIR=${2}

pushd $COMMIT_DIR

ID=$(basename $PWD)

REF_ID=$(basename ${REF_COMMIT_DIR})

for D in *; do
    if [ -d "${D}" ]; then
	STATFILE=${REF_COMMIT_DIR}/${REF_ID}_${D}_stats.json
	/var/opt/respdiff/statcmp.py -s "${STATFILE}" -c "${D}/respdiff.cfg" ${D}/*_report.json
	mv statplot_fields.svg ${ID}_vs_${REF_ID}_${D}.svg
    fi
done

popd
