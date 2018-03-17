#!/usr/bin/env python3

import argparse
import logging
import subprocess
from typing import Any, Mapping
import sys

import cfg
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
    logging.basicConfig(format='%(levelname)s %(message)s', level=logging.INFO)
    parser = argparse.ArgumentParser(
        description='attempt to reproduce original diffs from JSON report')
    parser.add_argument('-d', '--datafile', default='report.json',
                        help='JSON report file (default: report.json)')
    parser.add_argument('-c', '--config', default='respdiff.cfg', dest='cfgpath',
                        help='config file (default: respdiff.cfg)')
    parser.add_argument('envdir', type=str,
                        help='LMDB environment to read queries and answers from')
    args = parser.parse_args()
    config = cfg.read_cfg(args.cfgpath)
    report = DiffReport.from_json(args.datafile)
    criteria = config['diff']['criteria']
    timeout = config['sendrecv']['timeout']
    selector, sockets = sendrecv.sock_init(get_resolvers(config))
    restart_scripts = get_restart_scripts(config)

    if len(sockets) < len(config['servers']['names']):
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
            others_agree, mismatches = msgdiff.compare(answers, criteria, config['diff']['target'])

            reprocounter.retries += 1
            if others_agree:
                reprocounter.upstream_stable += 1
                if diff == Diff(diff.qid, mismatches):
                    reprocounter.verified += 1

    report.export_json(args.datafile)


if __name__ == '__main__':
    main()
