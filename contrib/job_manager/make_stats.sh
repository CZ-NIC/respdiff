#!/bin/bash

COMMIT_DIR=${1:-.}

pushd $COMMIT_DIR

ID=$(basename $PWD)

for D in *; do
    if [ -d "${D}" ]; then
        echo "${D}"   # your processing here
	# find "${D}" -name '*_report.json' | sed 's/report.json//' | xargs -I{} /var/opt/respdiff/diffsum.py --without-diffrepro -c "${D}/respdiff.cfg" -d {}report.json > {}report.txt /var/tmp/respdiff-db/shortlist
	STATFILE=${ID}_${D}_stats.json
	/var/opt/respdiff/sumstat.py -s "${STATFILE}" ${D}/*_report.json
	/var/opt/respdiff/statcmp.py -s "${STATFILE}" -c "${D}/respdiff.cfg"

	STATFILE=${ID}_${D}_stats.diffrepro.json
	/var/opt/respdiff/sumstat.py -s "${STATFILE}" ${D}/*_report.diffrepro.json
	/var/opt/respdiff/statcmp.py -s "${STATFILE}" -c "${D}/respdiff.cfg"
	mv statplot_fields.svg ${ID}_${D}.diffrepro.svg
    fi
done

popd
