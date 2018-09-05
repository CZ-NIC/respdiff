from itertools import zip_longest
import logging
from multiprocessing import pool
import random
import subprocess
from typing import (  # noqa
    AbstractSet, Any, Iterator, Iterable, Mapping, Optional, Set, Sequence, Tuple,
    TypeVar, Union)

from .database import (
    DNSRepliesFactory, DNSReply, key2qid, ResolverID, qid2key, QKey, WireFormat)
from .dataformat import Diff, DiffReport, FieldLabel, QID
from .match import compare
from .sendrecv import worker_perform_single_query
from .query import get_query_iterator


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


def chunker(iterable: Iterable[T], size: int) -> Iterator[Iterable[T]]:
    """
    Collect data into fixed-length chunks or blocks

    chunker([x, y, z], 2) --> [x, y], [z, None]
    """
    args = [iter(iterable)] * size
    return zip_longest(*args)


def process_answers(
            qkey: QKey,
            answers: Mapping[ResolverID, DNSReply],
            report: DiffReport,
            criteria: Sequence[FieldLabel],
            target: ResolverID
        ) -> None:
    if report.target_disagreements is None or report.reprodata is None:
        raise RuntimeError("Report doesn't contain necessary data!")
    qid = key2qid(qkey)
    reprocounter = report.reprodata[qid]
    others_agree, mismatches = compare(answers, criteria, target)

    reprocounter.retries += 1
    if others_agree:
        reprocounter.upstream_stable += 1
        assert mismatches is not None
        new_diff = Diff(qid, mismatches)
        if new_diff == report.target_disagreements[qid]:
            reprocounter.verified += 1
        elif new_diff:
            reprocounter.different_failure += 1


def query_stream_from_disagreements(
            lmdb,
            report: DiffReport,
            skip_unstable: bool = True,
            skip_non_reproducible: bool = True,
            shuffle: bool = True
        ) -> Iterator[Tuple[QKey, WireFormat]]:
    if report.target_disagreements is None or report.reprodata is None:
        raise RuntimeError("Report doesn't contain necessary data!")
    qids = report.target_disagreements.keys()  # type: Union[Sequence[QID], AbstractSet[QID]]
    if shuffle:
        # create a new, randomized list from disagreements
        qids = random.sample(qids, len(qids))
    queries = get_query_iterator(lmdb, qids)
    for qid, qwire in queries:
        diff = report.target_disagreements[qid]
        reprocounter = report.reprodata[qid]
        # verify if answers are stable
        if skip_unstable and reprocounter.retries != reprocounter.upstream_stable:
            logging.debug('Skipping QID %7d: unstable upstream', diff.qid)
            continue
        if skip_non_reproducible and reprocounter.retries != reprocounter.verified:
            logging.debug('Skipping QID %7d: not 100 %% reproducible', diff.qid)
            continue
        yield qid2key(qid), qwire


def query_stream_from_qids(
            lmdb,
            qids: Set[QID]
        ) -> Iterator[Tuple[QKey, WireFormat]]:
    queries = get_query_iterator(lmdb, random.sample(qids, len(qids)))
    for qid, qwire in queries:
        yield qid2key(qid), qwire


def reproduce_queries(
            query_stream: Iterator[Tuple[QKey, WireFormat]],
            report: DiffReport,
            dnsreplies_factory: DNSRepliesFactory,
            criteria: Sequence[FieldLabel],
            target: ResolverID,
            restart_scripts: Optional[Mapping[ResolverID, str]] = None,
            nproc: int = 1
        ) -> None:
    if restart_scripts is None:
        restart_scripts = {}
    with pool.Pool(processes=nproc) as p:
        done = 0
        for process_args in chunker(query_stream, nproc):
            # restart resolvers and clear their cache
            for script in restart_scripts.values():
                restart_resolver(script)

            process_args = [args for args in process_args if args is not None]
            for qkey, replies_data, in p.imap_unordered(
                    worker_perform_single_query,
                    process_args,
                    chunksize=1):
                replies = dnsreplies_factory.parse(replies_data)
                process_answers(qkey, replies, report, criteria, target)

            done += len(process_args)
            logging.info('Processed {:4d} queries'.format(done))
