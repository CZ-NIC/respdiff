#!/bin/bash
# Update and re-generate statistics from latest samples. Queue new jobs.
set -o errexit -o nounset -o xtrace

RESPDIFF_SRC=/var/opt/respdiff
JOBDIR=/var/tmp/respdiff-jobs
ADDDIR=${JOBDIR}/ref_additional
BUFFDIR=${JOBDIR}/buffer
MASTERDIR=${JOBDIR}/master

# create reference directory if it doesn't exist
mkdir -p ${MASTERDIR}
mkdir -p ${BUFFDIR}

# handle existing additional reference sample
if [ -h "${ADDDIR}" ]; then
    SAMPLE_NAME=$(basename $(readlink -f "${ADDDIR}"))

    # exit if sample jobs are still executing in condor (omit held jobs - status=5)
    if condor_q -c JobStatus!=5 -format "%s\n" JobBatchName | grep -qE "${SAMPLE_NAME}"; then
        exit 0
    fi

    pushd ${MASTERDIR}
    for TESTCASE in *; do
        if [[ -d "${TESTCASE}" && -d "${ADDDIR}/${TESTCASE}" ]]; then
            STATFILE="master_${TESTCASE}_stats.json"
            STATFILE_D="master_${TESTCASE}_stats.diffrepro.json"
            BUFFSTATFILE="${BUFFDIR}/buffer_${TESTCASE}_stats.json"
            BUFFSTATFILE_D="${BUFFDIR}/buffer_${TESTCASE}_stats.diffrepro.json"

            # match against reference
            set +o errexit
            ls ${ADDDIR}/${TESTCASE}/*_report.json &>/dev/null
            [ $? -ne 0 ] && continue
            ${RESPDIFF_SRC}/distrcmp.py -r "${STATFILE}" ${ADDDIR}/${TESTCASE}/*_report.json
            MATCH_STAT=$?

            ls ${ADDDIR}/${TESTCASE}/*_report.diffrepro.json &>/dev/null
            [ $? -ne 0 ] && continue
            ${RESPDIFF_SRC}/distrcmp.py -r "${STATFILE_D}" ${ADDDIR}/${TESTCASE}/*_report.diffrepro.json
            MATCH_STAT_D=$?
            set -o errexit
            MATCH_STAT_BOTH=$((${MATCH_STAT} + ${MATCH_STAT_D}))

            if [ ${MATCH_STAT_BOTH} -eq 0 ]; then
                # matches reference
                # clear buffer
                rm -rf ${BUFFDIR}/${TESTCASE} ${BUFFSTATFILE} ${BUFFSTATFILE_D}

                # extend reference
                cp -t ${MASTERDIR}/${TESTCASE}/ ${ADDDIR}/${TESTCASE}/*.json

                # delete all but last 50
                ls -1tr ${MASTERDIR}/${TESTCASE}/*_report.json | head -n -50 | xargs -d '\n' rm -f --
                ls -1tr ${MASTERDIR}/${TESTCASE}/*_report.diffrepro.json | head -n -50 | xargs -d '\n' rm -f --
            else
                if [ -f "${BUFFSTATFILE}" ]; then
                    # match against buffer
                    set +o errexit
                    ${RESPDIFF_SRC}/distrcmp.py -r "${BUFFSTATFILE}" ${ADDDIR}/${TESTCASE}/*_report.json
                    MATCH_BUFFSTAT=$?
                    ${RESPDIFF_SRC}/distrcmp.py -r "${BUFFSTATFILE_D}" ${ADDDIR}/${TESTCASE}/*_report.diffrepro.json
                    MATCH_BUFFSTAT_D=$?
                    set -o errexit
                    MATCH_BUFFSTAT_BOTH=$((${MATCH_BUFFSTAT} + ${MATCH_BUFFSTAT_D}))

                    if [ ${MATCH_BUFFSTAT_BOTH} -eq 0 ]; then
                        # doesn't match reference, matches buffer

                        # clear reference
                        rm -rf ${MASTERDIR}/${TESTCASE}

                        # create new reference from buff and new samples
                        mkdir -p ${MASTERDIR}/${TESTCASE}
                        cp -t ${MASTERDIR}/${TESTCASE}/ ${BUFFDIR}/${TESTCASE}/*.json
                        cp -t ${MASTERDIR}/${TESTCASE}/ ${ADDDIR}/${TESTCASE}/*.json

                        # clear buffer
                        rm -rf ${BUFFDIR}/${TESTCASE} ${BUFFSTATFILE} ${BUFFSTATFILE_D}
                    else
                        # doesn't match reference, nor buffer

                        # clear buffer
                        rm -rf ${BUFFDIR}/${TESTCASE} ${BUFFSTATFILE} ${BUFFSTATFILE_D}

                        # create new buffer
                        mkdir -p ${BUFFDIR}/${TESTCASE}
                        cp -ft ${BUFFDIR}/${TESTCASE}/ ${ADDDIR}/${TESTCASE}/*.json
                    fi
                else
                    # doesn't match reference, buffer was empty
                    # clear buffer (just in case)
                    rm -rf ${BUFFDIR}/${TESTCASE} ${BUFFSTATFILE} ${BUFFSTATFILE_D}

                    # create new buffer
                    mkdir -p ${BUFFDIR}/${TESTCASE}
                    cp -t ${BUFFDIR}/${TESTCASE}/ ${ADDDIR}/${TESTCASE}/*.json
                fi
            fi
        fi
    done
    popd

    # remove symlink
    rm ${ADDDIR}

    # update statistics
    ${RESPDIFF_SRC}/contrib/job_manager/make_stats.sh ${MASTERDIR}
    ${RESPDIFF_SRC}/contrib/job_manager/make_stats.sh ${BUFFDIR}

fi

# get master commit sha
rm -rf /tmp/knot-resolver
git clone --depth=1 https://gitlab.nic.cz/knot/knot-resolver.git /tmp/knot-resolver
pushd /tmp/knot-resolver
NEW_VERSION=$(git rev-parse --short origin/master)
popd

# submit new ref jobs to condor
NEW_LABEL=r$(date +%s)
${RESPDIFF_SRC}/contrib/job_manager/submit.py -p 0 -c 5 $(${RESPDIFF_SRC}/contrib/job_manager/create.py ${NEW_VERSION} -l ${NEW_LABEL})

# update the ref_additional link
pushd ${JOBDIR}
ln -sf "${NEW_VERSION}-${NEW_LABEL}" ref_additional
popd
