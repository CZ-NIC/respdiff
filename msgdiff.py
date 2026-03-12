#!/usr/bin/env python3

import argparse
from functools import partial
import logging
import multiprocessing.pool
import os
import pickle
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Tuple  # noqa

from respdiff import cli
from respdiff.dataformat import (
    DiffReport,
    Disagreements,
    DisagreementsCounter,
    FieldLabel,
    QID,
)
from respdiff.database import (
    DNSRepliesFactory,
    DNSReply,
    key2qid,
    LMDB,
    MetaDatabase,
    val2weight,
)
from respdiff.match import compare
from respdiff.typing import ResolverID

wrk_lmdb = None


def read_answers_lmdb(
    dnsreplies_factory: DNSRepliesFactory, qid: QID
) -> Mapping[ResolverID, DNSReply]:
    assert wrk_lmdb is not None, "LMDB wasn't initialized!"
    adb = wrk_lmdb.get_db(LMDB.ANSWERS)
    with wrk_lmdb.env.begin(adb) as txn:
        replies_blob = txn.get(qid)
    assert replies_blob
    return dnsreplies_factory.parse(replies_blob)


def compare_lmdb_wrapper(
    criteria: Sequence[FieldLabel],
    target: ResolverID,
    dnsreplies_factory: DNSRepliesFactory,
    qid: QID,
) -> None:
    assert wrk_lmdb is not None, "LMDB wasn't initialized!"
    answers = read_answers_lmdb(dnsreplies_factory, qid)
    others_agree, target_diffs = compare(answers, criteria, target)
    if others_agree and not target_diffs:
        return  # all agreed, nothing to write
    blob = pickle.dumps((others_agree, target_diffs))
    ddb = wrk_lmdb.get_db(LMDB.DIFFS)
    with wrk_lmdb.env.begin(ddb, write=True) as txn:
        txn.put(qid, blob)


def export_json(lmdb: LMDB, filename: str, report: DiffReport):
    report.other_disagreements = DisagreementsCounter()
    report.target_disagreements = Disagreements()

    # get diff data
    ddb = lmdb.get_db(LMDB.DIFFS)
    wdb = lmdb.get_db(LMDB.WEIGHTS)
    with lmdb.env.begin(ddb) as txn:
        with txn.cursor() as diffcur:
            for key, diffblob in diffcur:
                qid = key2qid(key)
                weight = val2weight(txn.get(db=wdb, key=key))
                others_agree, diff = pickle.loads(diffblob)
                if not others_agree:
                    report.other_disagreements.queries.add(qid)
                else:
                    for field, mismatch in diff.items():
                        report.target_disagreements.add_mismatch(
                            field, mismatch, qid, weight
                        )

    # NOTE: msgdiff is the first tool in the toolchain to generate report.json
    #       thus it doesn't make sense to re-use existing report.json file
    if os.path.exists(filename):
        backup_filename = filename + ".bak"
        os.rename(filename, backup_filename)
        logging.warning(
            "JSON report already exists, overwriting file. Original "
            "file backed up as %s",
            backup_filename,
        )
    report.export_json(filename)


def prepare_report(lmdb_, servers: Sequence[ResolverID]) -> DiffReport:
    qdb = lmdb_.open_db(LMDB.QUERIES)
    adb = lmdb_.open_db(LMDB.ANSWERS)
    wdb = lmdb_.open_db(LMDB.WEIGHTS)

    with lmdb_.env.begin() as txn:
        with txn.cursor(db=wdb) as wcur:
            total_queries = sum(
                val2weight(rawweight)
                for rawweight in wcur.iternext(keys=False, values=True)
            )
        with txn.cursor(db=adb) as acur:
            total_answers = sum(
                val2weight(txn.get(db=wdb, key=answerkey))
                for answerkey in acur.iternext(keys=True, values=False)
            )

    meta = MetaDatabase(lmdb_, servers)
    start_time = meta.read_start_time()
    end_time = meta.read_end_time()

    return DiffReport(start_time, end_time, total_queries, total_answers)


def wrk_lmdb_init(envdir):
    """Each worker process has it's own LMDB connection"""
    global wrk_lmdb

    wrk_lmdb = LMDB(envdir, fast=True)
    wrk_lmdb.open_db(LMDB.ANSWERS)
    wrk_lmdb.open_db(LMDB.DIFFS)


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description="compute diff from answers stored in LMDB and write diffs to LMDB"
    )
    cli.add_arg_envdir(parser)
    cli.add_arg_config(parser)
    cli.add_arg_datafile(parser)

    args = parser.parse_args()
    datafile = cli.get_datafile(args, check_exists=False)
    criteria = args.cfg["diff"]["criteria"]
    target = args.cfg["diff"]["target"]
    servers = args.cfg["servers"]["names"]

    multiprocessing.set_start_method("forkserver")

    with LMDB(args.envdir) as lmdb:
        # NOTE: To avoid an lmdb.BadRslotError, probably caused by weird
        # interaction when using multiple transaction / processes, open a separate
        # environment. Also, any dbs have to be opened before using MetaDatabase().
        report = prepare_report(lmdb, servers)
        cli.check_metadb_servers_version(lmdb, servers)
        # sanity check we have some answers
        lmdb.open_db(LMDB.ANSWERS)
        # prepare state shared by all workers
        lmdb.open_db(LMDB.DIFFS, create=True, drop=True)

    with LMDB(args.envdir, readonly=True) as lmdb:
        lmdb.open_db(LMDB.ANSWERS)
        lmdb.open_db(LMDB.DIFFS)
        lmdb.open_db(LMDB.WEIGHTS)
        qid_stream = lmdb.key_stream(LMDB.ANSWERS)

        dnsreplies_factory = DNSRepliesFactory(servers)
        compare_func = partial(
            compare_lmdb_wrapper, criteria, target, dnsreplies_factory
        )
        with multiprocessing.pool.Pool(
            initializer=wrk_lmdb_init, initargs=(args.envdir,)
        ) as p:
            for _ in p.imap_unordered(compare_func, qid_stream, chunksize=10):
                pass
        export_json(lmdb, datafile, report)


if __name__ == "__main__":
    main()
