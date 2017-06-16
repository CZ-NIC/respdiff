#!/usr/bin/env python3

import argparse
import logging
import multiprocessing.pool as pool
import struct
import sys

import dns.exception
import dns.message
import dns.rdatatype
import lmdb

import blacklist
import dbhelper


QUERIES_DB_NAME = b'queries'
REPORT_CHUNKS = 10000


def read_lines(instream):
    """
    Yield (line number, stripped line text). Skip empty lines.
    """
    i = 0
    for line in instream:
        line = line.strip()
        if line:
            i += 1
            yield (i, line)
            if i % REPORT_CHUNKS == 0:
                logging.info('Read %d queries', i)


def int_or_fromtext(value, fromtext):
    try:
        return int(value)
    except ValueError:
        return fromtext(value)


def q_fromtext(line):
    """
    Convert line from <qname> <RR type> to DNS query in IN class.

    Returns: DNS message object
    Raises: ValueError or dns.exception.Exception on invalid input
    """
    qname, qtype = line.rsplit(None, 1)
    qname = dns.name.from_text(qname)
    qtype = int_or_fromtext(qtype, dns.rdatatype.from_text)
    return dns.message.make_query(qname, qtype, dns.rdataclass.IN,
                                  want_dnssec=True, payload=4096)


def wrk_lmdb_init(envdir):
    """
    Worker: initialize LMDB env and open 'queries' database
    """
    global env
    global db

    config = dbhelper.env_open.copy()
    config.update({
        'path': envdir,
        'sync': False,    # unsafe but fast
        'writemap': True  # we do not care, this is a new database
        })
    env = lmdb.Environment(**config)
    db = env.open_db(key=b'queries', **dbhelper.db_open)


def wrk_lmdb_write(qid, wire):
    """
    Worker: write query wire format into database
    """
    global env
    global db

    key = dbhelper.qid2key(qid)
    with env.begin(db, write=True) as txn:
        txn.put(key, wire)


def wrk_process_line(args):
    """
    Worker: parse input line and write (qid, wire formt) to LMDB queries DB

    Skips over empty lines, raises for malformed inputs.
    """
    qid, line = args
    try:
        msg = q_fromtext(line)
        if not blacklist.obj_blacklisted(msg):
            wrk_lmdb_write(qid, msg.to_wire())
        else:
            logging.debug('Query "%s" blacklisted (skipping query ID %d)', line, qid)
    except (ValueError, struct.error, dns.exception.DNSException) as ex:
        logging.error('Invalid query "%s": %s (skipping query ID %d)', line, ex, qid)
        return


def main():
    logging.basicConfig(format='%(levelname)s %(message)s', level=logging.DEBUG)
    parser = argparse.ArgumentParser(
        description='Convert text list of queries from standard input '
                    'and store wire format into LMDB "queries" DB. '
                    'Expected query format is: "<qname> <RR type>", '
                    'one query per line.')
    parser.add_argument('envpath', type=str,
                        help='path where to create LMDB environment')
    args = parser.parse_args()

    if dbhelper.db_exists(args.envpath, QUERIES_DB_NAME):
        logging.critical(
            'LMDB environment "%s" already contains DB %s! '
            'Overwritting it would invalidate data in the environment, '
            'terminating.',
            args.envpath, QUERIES_DB_NAME)
        sys.exit(1)

    qstream = read_lines(sys.stdin)
    with pool.Pool(initializer=wrk_lmdb_init, initargs=(args.envpath,)) as workers:
        for _ in workers.imap_unordered(wrk_process_line, qstream, chunksize=1000):
            pass

if __name__ == '__main__':
    main()
