#!/usr/bin/env python3
import argparse
import collections
import contextlib
import glob
import itertools
import logging
import os
import sys
import time
import traceback
from typing import Dict, List, Sequence, Tuple  # noqa
import warnings


WAIT_POLLING_PERIOD = 30
JOB_STATUS_RUNNING = 2


def get_all_files(directory: str) -> List[str]:
    files = []
    for filename in glob.iglob("{}/**".format(directory), recursive=True):
        # omit job artifacts (begins with j*)
        if os.path.isfile(filename) and not os.path.basename(filename).startswith("j"):
            files.append(os.path.relpath(filename, directory))
    return files


def condor_submit(txn, priority: int) -> int:
    directory = os.getcwd()
    input_files = get_all_files(directory)

    if "run_respdiff.sh" in input_files:
        executable = "run_respdiff.sh"
        output_files = [
            "j$(Cluster).$(Process)_docker.txt",
            "j$(Cluster).$(Process)_report.json",
            "j$(Cluster).$(Process)_report.diffrepro.json",
            "j$(Cluster).$(Process)_report.txt",
            "j$(Cluster).$(Process)_report.diffrepro.txt",
            "j$(Cluster).$(Process)_histogram.tar.gz",
            "j$(Cluster).$(Process)_logs.tar.gz",
        ]
        if "stats.json" in input_files:
            output_files.extend(
                [
                    "j$(Cluster).$(Process)_report.noref.json",
                    "j$(Cluster).$(Process)_report.noref.txt",
                    "j$(Cluster).$(Process)_report.diffrepro.noref.json",
                    "j$(Cluster).$(Process)_report.diffrepro.noref.txt",
                    # 'j$(Cluster).$(Process)_dnsviz.json.gz',
                    # 'j$(Cluster).$(Process)_report.noref.dnsviz.json',
                    # 'j$(Cluster).$(Process)_report.noref.dnsviz.txt',
                ]
            )
    elif "run_resperf.sh" in input_files:
        executable = "run_resperf.sh"
        output_files = [
            "j$(Cluster).$(Process)_exitcode",
            "j$(Cluster).$(Process)_docker.txt",
            "j$(Cluster).$(Process)_resperf.txt",
            "j$(Cluster).$(Process)_logs.tar.gz",
        ]
    elif "run_distrotest.sh" in input_files:
        executable = "run_distrotest.sh"
        output_files = [
            "j$(Cluster).$(Process)_exitcode",
            "j$(Cluster).$(Process)_vagrant.log.txt",
        ]
    else:
        raise RuntimeError(
            "The provided directory doesn't look like a respdiff/resperf job. "
            "{}/run_*.sh is missing!".format(directory)
        )

    # create batch name from dir structure
    commit_dir_path, test_case = os.path.split(directory)
    _, commit_dir = os.path.split(commit_dir_path)
    batch_name = commit_dir + "_" + test_case

    submit = Submit(
        {
            "priority": str(priority),
            "executable": executable,
            "arguments": "$(Cluster) $(Process)",
            "error": "j$(Cluster).$(Process)_stderr.txt",
            "output": "j$(Cluster).$(Process)_stdout.txt",
            "log": "j$(Cluster).$(Process)_log.txt",
            "jobbatchname": batch_name,
            "should_transfer_files": "YES",
            "when_to_transfer_output": "ON_EXIT",
            "transfer_input_files": ", ".join(input_files),
            "transfer_output_files": ", ".join(output_files),
        }
    )
    return submit.queue(txn)


@contextlib.contextmanager
def pushd(new_dir):
    previous_dir = os.getcwd()
    os.chdir(new_dir)
    yield
    os.chdir(previous_dir)


def condor_wait_for(schedd, job_ids: Sequence[int]) -> None:
    prev_remaining = None
    prev_running = None
    prev_worst_pos = None

    while True:
        remaining, running, worst_pos = condor_check_status(schedd, job_ids)
        if not remaining:
            break

        # log only status changes
        if (
            remaining != prev_remaining
            or running != prev_running
            or worst_pos != prev_worst_pos
        ):
            logging.info(
                "  remaning: %2d (running: %2d)     worst queue position: %2d",
                remaining,
                running,
                worst_pos + 1,
            )

        prev_remaining = remaining
        prev_running = running
        prev_worst_pos = worst_pos

        time.sleep(WAIT_POLLING_PERIOD)


def condor_check_status(schedd, job_ids: Sequence[int]) -> Tuple[int, int, int]:
    all_jobs = schedd.query(True, ["JobPrio", "ClusterId", "ProcId", "JobStatus"])
    all_jobs = sorted(
        all_jobs, key=lambda x: (-x["JobPrio"], x["ClusterId"], x["ProcId"])
    )

    worst_pos = 0
    running = 0
    remaining = 0

    for i, job in enumerate(all_jobs):
        if int(job["ClusterId"]) in job_ids:
            remaining += 1
            if int(job["JobStatus"]) == JOB_STATUS_RUNNING:
                running += 1
            worst_pos = i

    return remaining, running, worst_pos


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit prepared jobs to HTCondor cluster"
    )
    parser.add_argument(
        "-c",
        "--count",
        type=int,
        default=1,
        help="How many times to submit job (default: 1)",
    )
    parser.add_argument(
        "-p",
        "--priority",
        type=int,
        default=5,
        help="Set condor job priority, higher means sooner execution (default: 5)",
    )
    parser.add_argument(
        "-w",
        "--wait",
        action="store_true",
        help="Wait until all submitted jobs are finished",
    )
    parser.add_argument(
        "job_dir", nargs="+", help="Path to the job directory to be submitted"
    )

    args = parser.parse_args()

    job_ids = collections.defaultdict(list)  # type: Dict[str, List[int]]
    schedd = Schedd()

    with schedd.transaction() as txn:
        # submit jobs one-by-one to ensure round-robin job execution (instead of seq)
        for _ in range(args.count):
            for directory in args.job_dir:
                with pushd(directory):
                    job_ids[directory].append(condor_submit(txn, args.priority))

    for directory, jobs in job_ids.items():
        logging.info("%s JOB ID(s): %s", directory, ", ".join(str(j) for j in jobs))

    job_count = sum(len(jobs) for jobs in job_ids.values())
    logging.info("%d job(s) successfully submitted!", job_count)

    if args.wait:
        logging.info(
            "WAITING for jobs to complete. This can be safely interrupted with Ctl+C..."
        )
        try:
            condor_wait_for(schedd, list(itertools.chain(*job_ids.values())))
        except KeyboardInterrupt:
            pass
        else:
            logging.info("All jobs done!")


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s %(levelname)8s  %(message)s", level=logging.DEBUG
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # trigger UserWarning which causes ImportError
        try:
            from htcondor import Submit, Schedd
        except (ImportError, UserWarning):
            logging.error("HTCondor not detected. Use this script on a submit machine.")
            sys.exit(1)

    try:
        main()
    except RuntimeError as exc:
        logging.debug(traceback.format_exc())
        logging.error(str(exc))
        sys.exit(1)
    except Exception as exc:
        logging.debug(traceback.format_exc())
        logging.critical("Unhandled code exception: %s", str(exc))
        sys.exit(2)
