#!/usr/bin/env python3

import argparse
from functools import partial
import logging
import multiprocessing.pool as pool
import os
import pickle
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Tuple  # noqa
import sys

import dns.exception
import dns.message

from respdiff import cli
from respdiff.dataformat import (
    DiffReport, Disagreements, DisagreementsCounter, FieldLabel, QID)
from respdiff.dbhelper import DNSRepliesFactory, key2qid, LMDB, MetaDatabase, ResolverID
from respdiff.match import compare


lmdb = None


def read_answers_lmdb(
            dnsreplies_factory: DNSRepliesFactory,
            qid: QID
        ) -> Mapping[ResolverID, dns.message.Message]:
    assert lmdb is not None, "LMDB wasn't initialized!"
    adb = lmdb.get_db(LMDB.ANSWERS)
    with lmdb.env.begin(adb) as txn:
        replies_blob = txn.get(qid)
    assert replies_blob
    replies = dnsreplies_factory.parse(replies_blob)
    return dnsreplies_factory.decode_parsed(replies)


def compare_lmdb_wrapper(
            criteria: Sequence[FieldLabel],
            target: ResolverID,
            dnsreplies_factory: DNSRepliesFactory,
            qid: QID
        ) -> None:
    assert lmdb is not None, "LMDB wasn't initialized!"
    answers = read_answers_lmdb(dnsreplies_factory, qid)
    others_agree, target_diffs = compare(answers, criteria, target)
    if others_agree and not target_diffs:
        return  # all agreed, nothing to write
    blob = pickle.dumps((others_agree, target_diffs))
    ddb = lmdb.get_db(LMDB.DIFFS)
    with lmdb.env.begin(ddb, write=True) as txn:
        txn.put(qid, blob)


def export_json(filename: str, report: DiffReport):
    assert lmdb is not None, "LMDB wasn't initialized!"
    report.other_disagreements = DisagreementsCounter()
    report.target_disagreements = Disagreements()

    # get diff data
    ddb = lmdb.get_db(LMDB.DIFFS)
    with lmdb.env.begin(ddb) as txn:
        with txn.cursor() as diffcur:
            for key, diffblob in diffcur:
                qid = key2qid(key)
                others_agree, diff = pickle.loads(diffblob)
                if not others_agree:
                    report.other_disagreements.count += 1
                else:
                    for field, mismatch in diff.items():
                        report.target_disagreements.add_mismatch(field, mismatch, qid)

    # NOTE: msgdiff is the first tool in the toolchain to generate report.json
    #       thus it doesn't make sense to re-use existing report.json file
    if os.path.exists(filename):
        backup_filename = filename + '.bak'
        os.rename(filename, backup_filename)
        logging.warning(
            'JSON report already exists, overwriting file. Original '
            'file backed up as %s', backup_filename)
    report.export_json(filename)


def prepare_report(lmdb_, servers: Sequence[ResolverID]) -> DiffReport:
    qdb = lmdb_.open_db(LMDB.QUERIES)
    adb = lmdb_.open_db(LMDB.ANSWERS)
    with lmdb_.env.begin() as txn:
        total_queries = txn.stat(qdb)['entries']
        total_answers = txn.stat(adb)['entries']

    meta = MetaDatabase(lmdb_, servers)
    start_time = meta.read_start_time()
    end_time = meta.read_end_time()

    return DiffReport(
        start_time,
        end_time,
        total_queries,
        total_answers)


def main():
    global lmdb

    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description='compute diff from answers stored in LMDB and write diffs to LMDB')
    cli.add_arg_envdir(parser)
    cli.add_arg_config(parser)
    cli.add_arg_datafile(parser)

    args = parser.parse_args()
    datafile = cli.get_datafile(args, check_exists=False)
    criteria = args.cfg['diff']['criteria']
    target = args.cfg['diff']['target']
    servers = args.cfg['servers']['names']

    with LMDB(args.envdir) as lmdb_:
        # NOTE: To avoid an lmdb.BadRslotError, probably caused by weird
        # interaction when using multiple transaction / processes, open a separate
        # environment. Also, any dbs have to be opened before using MetaDatabase().
        report = prepare_report(lmdb_, servers)
        try:
            MetaDatabase(lmdb_, servers, create=False)  # check version and servers
        except NotImplementedError as exc:
            logging.critical(exc)
            sys.exit(1)

    with LMDB(args.envdir, fast=True) as lmdb_:
        lmdb = lmdb_
        lmdb.open_db(LMDB.ANSWERS)
        lmdb.open_db(LMDB.DIFFS, create=True, drop=True)
        qid_stream = lmdb.key_stream(LMDB.ANSWERS)

        dnsreplies_factory = DNSRepliesFactory(servers)
        compare_func = partial(
            compare_lmdb_wrapper, criteria, target, dnsreplies_factory)
        with pool.Pool() as p:
            for _ in p.imap_unordered(compare_func, qid_stream, chunksize=10):
                pass
        export_json(datafile, report)


if __name__ == '__main__':
    main()
