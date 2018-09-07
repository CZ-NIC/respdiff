#!/bin/bash
# Update and re-generate statistics from latest samples. Queue new jobs.
set -o errexit -o nounset -o xtrace

RESPDIFF_SRC=/var/opt/respdiff
JOBDIR=/var/tmp/respdiff-jobs
ADDDIR=${JOBDIR}/ref_additional
MASTERDIR=${JOBDIR}/master

# handle existing additional reference sample
if [ -h "${ADDDIR}" ]; then
    SAMPLE_NAME=$(basename $(readlink -f "${ADDDIR}"))

    # if sample job is still executing, exit
    if condor_q  -format "%s\n" JobBatchName | grep -qE "${SAMPLE_NAME}"; then
        exit 0
    fi

    # copy JSON reports to reference set
    mkdir -p ${MASTERDIR}
    rsync -amv --include '*.json' -f 'hide,! */' ${ADDDIR}/ ${MASTERDIR}
fi

# delete reports older than 48h
find ${MASTERDIR} -type f -mtime +1 -delete

# update statistics
${RESPDIFF_SRC}/contrib/job_manager/make_stats.sh ${MASTERDIR}

# get master commit sha
rm -rf /tmp/knot-resolver
git clone --depth=1 https://gitlab.labs.nic.cz/knot/knot-resolver.git /tmp/knot-resolver
pushd /tmp/knot-resolver
NEW_VERSION=$(git rev-parse --short origin/master)
popd

# submit new ref jobs to condor
NEW_LABEL=r$(date +%s)
${RESPDIFF_SRC}/contrib/job_manager/submit.py -p 0 -c 2 $(${RESPDIFF_SRC}/contrib/job_manager/create.py ${NEW_VERSION} -l ${NEW_LABEL})

# update the ref_additional link
pushd ${JOBDIR}
ln -sf "${NEW_VERSION}-${NEW_LABEL}" ref_additional
popd
