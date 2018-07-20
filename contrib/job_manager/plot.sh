#!/bin/bash

COMMIT_DIR=${1:-.}

pushd $COMMIT_DIR

ID=$(basename $PWD)
ID=${ID:0:7}

for D in *; do
    if [ -d "${D}" ]; then
        echo "${D}"   # your processing here
	STATFILE=${ID}_${D}_stats.json
	/var/opt/respdiff/sumstat.py -s "${STATFILE}" ${D}/*_report.json
	/var/opt/respdiff/statcmp.py -s "${STATFILE}" -c "${D}/respdiff.cfg"
	mv statplot_fields.svg ${ID}_${D}.svg
    fi
done

popd
