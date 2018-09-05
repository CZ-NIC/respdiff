#!/usr/bin/env python3

import argparse
import logging
import sys
from typing import (  # noqa
    Any, AbstractSet, Iterable, Iterator, Mapping, Sequence, Tuple, TypeVar,
    Union)

from respdiff import cli
from respdiff.database import LMDB
from respdiff.dataformat import Diff, DiffReport, FieldLabel, ReproData, QID  # noqa
from respdiff.query import get_query_iterator, qwire_to_qname_qtype


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description='attempt to reproduce original diffs from JSON report')
    cli.add_arg_envdir(parser)
    cli.add_arg_config(parser)
    cli.add_arg_datafile(parser)
    cli.add_arg_stats(parser)

    args = parser.parse_args()
    stats = args.stats

    if stats.queries is None:
        logging.critical("Statistics file contains no query information!")
        sys.exit(1)

    datafile = cli.get_datafile(args)
    report = DiffReport.from_json(datafile)

    verified_failing = stats.queries.get_unseen_failures(report, verified=True)
    # verified_fixed = stats.queries.get_fixed_queries(report, verified=True)

    with LMDB(args.envdir, readonly=True) as lmdb:
        lmdb.open_db(LMDB.QUERIES)

        print('VERIFIED NEW FAILING: {}'.format(len(verified_failing)))
        for qid, qwire in get_query_iterator(lmdb, verified_failing):
            qname = qwire_to_qname_qtype(qwire)
            reprocounter = report.reprodata[qid]
            if reprocounter.verified > reprocounter.different_failure:
                diff = report.target_disagreements[qid]
                print('{}: {}'.format(qname, diff))
            else:
                print('{}: ???'.format(qname))


if __name__ == '__main__':
    main()
