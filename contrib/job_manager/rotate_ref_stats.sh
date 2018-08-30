#!/bin/bash
# Create new statistics from finished ref jobs and submit new ref jobs

set -o errexit -o nounset -o xtrace

RESPDIFF_SRC=/var/opt/respdiff
JOBDIR=/var/tmp/respdiff-jobs

NEW_VERSION=${1}
COUNT=${2:-100}
NEW_LABEL=$(date +%Y%m%d)

test -d ${JOBDIR}/ref_next
test ! -d ${JOBDIR}/${NEW_VERSION}-${NEW_LABEL}

# create statistics for the finished set
${RESPDIFF_SRC}/contrib/job_manager/make_stats.sh ${JOBDIR}/ref_next

# submit new ref jobs to condor
${RESPDIFF_SRC}/contrib/job_manager/submit.py -p 0 -c ${COUNT} $(${RESPDIFF_SRC}/contrib/job_manager/create.py ${NEW_VERSION} -l ${NEW_LABEL})

# make the finished reference set the current one
mv -T ${JOBDIR}/ref_{next,current}

# make the newly submitted ref set the next one
pushd ${JOBDIR}
ln -sf "${NEW_VERSION}-${NEW_LABEL}" ref_next
popd

echo "Success!"
