#!/usr/bin/env python3
import argparse
import collections
import contextlib
import glob
import logging
import os
import sys
import traceback
from typing import List
import warnings


def get_all_files(directory: str) -> List[str]:
    files = []
    for filename in glob.iglob('{}/**'.format(directory), recursive=True):
        if os.path.isfile(filename):
            files.append(os.path.relpath(filename, directory))
    return files


def submit_condor_job(txn, priority: int) -> int:
    directory = os.getcwd()
    input_files = get_all_files(directory)

    # TODO: may not be necesary - handled by condor runtime exception?
    if 'run_respdiff.sh' not in input_files:
        raise RuntimeError(
            "The provided directory doesn't look like a respdiff job. "
            "{}/run_respdiff.sh is missing!".format(directory))

    # create batch name from dir structure
    commit_dir_path, test_case = os.path.split(directory)
    _, commit_dir = os.path.split(commit_dir_path)
    batch_name = commit_dir + '_' + test_case

    submit = Submit({
        'priority': str(priority),
        'executable': 'run_respdiff.sh',
        'arguments': '$(Cluster) $(Process)',
        'error': 'j$(Cluster).$(Process)_stderr',
        'output': 'j$(Cluster).$(Process)_stdout',
        'log': 'j$(Cluster).$(Process)_log',
        'jobbatchname': batch_name,
        'should_transfer_files': 'YES',
        'when_to_transfer_output': 'ON_EXIT',
        'transfer_input_files': ', '.join(input_files),
        'transfer_output_files': ', '.join([
            'j$(Cluster).$(Process)_report.json',
            'j$(Cluster).$(Process)_report.txt',
            'j$(Cluster).$(Process)_histogram.svg']),
        })
    return submit.queue(txn)


@contextlib.contextmanager
def pushd(new_dir):
    previous_dir = os.getcwd()
    os.chdir(new_dir)
    yield
    os.chdir(previous_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit prepared jobs to HTCondor cluster")
    parser.add_argument(
        '-c', '--count', type=int, default=1,
        help="How many times to submit job (default: 1)")
    parser.add_argument(
        '-p', '--priority', type=int, default=5,
        help="Set condor job priority, higher means sooner execution (default: 5)")
    parser.add_argument(
        '-w', '--wait', action='store_true',
        help="Wait until all submitted jobs are finished")
    parser.add_argument(
        'job_dir', nargs='+',
        help="Path to the job directory to be submitted")

    args = parser.parse_args()

    job_ids = collections.defaultdict(list)
    schedd = Schedd()

    with schedd.transaction() as txn:
        # submit jobs one-by-one to ensure round-robin job execution (instead of seq)
        for _ in range(args.count):
            for directory in args.job_dir:
                with pushd(directory):
                    job_ids[directory].append(submit_condor_job(txn, args.priority))

    for directory, jobs in job_ids.items():
        logging.debug("%s job ids: %s", directory, ', '.join(str(j) for j in jobs))

    job_count = sum(len(jobs) for jobs in job_ids.values())
    logging.info("%d jobs successfully submitted!", job_count)

    if args.wait:
        raise NotImplementedError("Waiting for jobs not implemented yet!")


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s %(levelname)8s  %(message)s', level=logging.DEBUG)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        try:
            from htcondor import Submit, Schedd
        except ImportError:
            logging.error('HTCondor not detected. Use this script on a submit machine.')
            sys.exit(1)

    try:
        main()
    except RuntimeError as exc:
        logging.debug(traceback.format_exc())
        logging.error(str(exc))
        sys.exit(1)
    except Exception as exc:
        logging.debug(traceback.format_exc())
        logging.critical('Unhandled code exception: %s', str(exc))
        sys.exit(2)
