#!/usr/bin/env python3

import argparse
import logging
import subprocess
from typing import Any, Mapping
import sys

import cli
from dbhelper import LMDB
import diffsum
from dataformat import Diff, DiffReport, ReproData, ResolverID
import msgdiff
from orchestrator import get_resolvers
import sendrecv


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


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description='attempt to reproduce original diffs from JSON report')
    cli.add_arg_envdir(parser)
    cli.add_arg_config(parser)
    cli.add_arg_datafile(parser)

    args = parser.parse_args()
    datafile = cli.get_datafile(args)
    report = DiffReport.from_json(datafile)
    criteria = args.cfg['diff']['criteria']
    timeout = args.cfg['sendrecv']['timeout']
    selector, sockets = sendrecv.sock_init(get_resolvers(args.cfg))
    restart_scripts = get_restart_scripts(args.cfg)

    if len(sockets) < len(args.cfg['servers']['names']):
        logging.critical("Couldn't create sockets for all resolvers.")
        sys.exit(1)

    if report.reprodata is None:
        report.reprodata = ReproData()

    with LMDB(args.envdir, readonly=True) as lmdb:
        lmdb.open_db(LMDB.QUERIES)
        queries = diffsum.get_query_iterator(lmdb, report.target_disagreements)

        for qid, qwire in queries:
            diff = report.target_disagreements[qid]
            reprocounter = report.reprodata[qid]
            # verify if answers are stable
            if reprocounter.retries != reprocounter.upstream_stable:
                logging.debug('Skipping QID %d: unstable upstream', diff.qid)
                continue

            for script in restart_scripts.values():
                restart_resolver(script)

            wire_blobs, _ = sendrecv.send_recv_parallel(qwire, selector, sockets, timeout)
            answers = msgdiff.decode_wire_dict(wire_blobs)
            others_agree, mismatches = msgdiff.compare(
                answers, criteria, args.cfg['diff']['target'])

            reprocounter.retries += 1
            if others_agree:
                reprocounter.upstream_stable += 1
                if diff == Diff(diff.qid, mismatches):
                    reprocounter.verified += 1

    report.export_json(datafile)


if __name__ == '__main__':
    main()
