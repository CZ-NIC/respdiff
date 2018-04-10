#!/usr/bin/env python3

import argparse
from itertools import zip_longest
import logging
from multiprocessing import pool
import pickle
import random
import subprocess
from typing import Any, Iterable, Iterator, Mapping, Sequence, Tuple, TypeVar

import cli
from dbhelper import LMDB, qid2key, key2qid, QKey
import diffsum
from dataformat import Diff, DiffReport, FieldLabel, ReproData, WireFormat
import msgdiff
import sendrecv
from sendrecv import ResolverID, RepliesBlob


T = TypeVar('T')


def restart_resolver(script_path: str) -> None:
    try:
        subprocess.check_call(script_path)
    except subprocess.CalledProcessError as exc:
        logging.warning('Resolver restart failed (exit code %d): %s',
                        exc.returncode, script_path)
    except PermissionError as exc:
        logging.warning('Resolver restart failed (permission error): %s',
                        script_path)


def get_restart_scripts(config: Mapping[str, Any]) -> Mapping[ResolverID, str]:
    restart_scripts = {}
    for resolver in config['servers']['names']:
        try:
            restart_scripts[resolver] = config[resolver]['restart_script']
        except KeyError:
            logging.warning('No restart script available for "%s"!', resolver)
    return restart_scripts


def disagreement_query_stream(
            lmdb,
            report: DiffReport,
            skip_unstable: bool = True,
            shuffle: bool = True
        ) -> Iterator[Tuple[QKey, WireFormat]]:
    qids = report.target_disagreements.keys()
    if shuffle:
        # create a new, randomized list from disagreements
        qids = set(random.sample(qids, len(qids)))
    queries = diffsum.get_query_iterator(lmdb, qids)
    for qid, qwire in queries:
        diff = report.target_disagreements[qid]
        reprocounter = report.reprodata[qid]
        # verify if answers are stable
        if skip_unstable and reprocounter.retries != reprocounter.upstream_stable:
            logging.debug('Skipping QID %d: unstable upstream', diff.qid)
            continue
        yield qid2key(qid), qwire


def chunker(iterable: Iterable[T], size: int) -> Iterator[Iterable[T]]:
    """
    Collect data into fixed-length chunks or blocks

    chunker([x, y, z], 2) --> [x, y], [z, None]
    """
    args = [iter(iterable)] * size
    return zip_longest(*args)


def process_answers(
            qkey: QKey,
            replies: RepliesBlob,
            report: DiffReport,
            criteria: Sequence[FieldLabel],
            target: ResolverID
        ) -> None:
    qid = key2qid(qkey)
    reprocounter = report.reprodata[qid]
    wire_dict = pickle.loads(replies)
    answers = msgdiff.decode_wire_dict(wire_dict)
    others_agree, mismatches = msgdiff.compare(answers, criteria, target)

    reprocounter.retries += 1
    if others_agree:
        reprocounter.upstream_stable += 1
        if Diff(qid, mismatches) == report.target_disagreements[qid]:
            reprocounter.verified += 1


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description='attempt to reproduce original diffs from JSON report')
    cli.add_arg_envdir(parser)
    cli.add_arg_config(parser)
    cli.add_arg_datafile(parser)
    parser.add_argument('-s', '--sequential', action='store_true', default=False,
                        help='send one query at a time (slower, but more reliable)')

    args = parser.parse_args()
    sendrecv.module_init(args)
    datafile = cli.get_datafile(args)
    report = DiffReport.from_json(datafile)
    restart_scripts = get_restart_scripts(args.cfg)

    if args.sequential:
        nproc = 1
    else:
        nproc = args.cfg['sendrecv']['jobs']

    if report.reprodata is None:
        report.reprodata = ReproData()

    with LMDB(args.envdir, readonly=True) as lmdb:
        lmdb.open_db(LMDB.QUERIES)

        dstream = disagreement_query_stream(lmdb, report)
        try:
            with pool.Pool(processes=nproc) as p:
                done = 0
                for process_args in chunker(dstream, nproc):
                    # restart resolvers and clear their cache
                    for script in restart_scripts.values():
                        restart_resolver(script)

                    process_args = [args for args in process_args if args is not None]
                    for qkey, replies, in p.imap_unordered(
                            sendrecv.worker_perform_single_query,
                            process_args,
                            chunksize=1):
                        process_answers(qkey, replies, report,
                                        args.cfg['diff']['criteria'],
                                        args.cfg['diff']['target'])

                    done += len(process_args)
                    logging.info('Processed {:4d} queries'.format(done))
        finally:
            # make sure data is saved in case of interrupt
            report.export_json(datafile)


if __name__ == '__main__':
    main()
