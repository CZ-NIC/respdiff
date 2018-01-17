#!/usr/bin/env python3

import argparse
import logging
import multiprocessing.pool as pool
import struct
import sys
from typing import Tuple

import dpkt

import blacklist
import dbhelper
import dns.exception
import dns.message
import dns.rdatatype
import lmdb

REPORT_CHUNKS = 10000


def read_lines(instream):
    """
    Yield (line number, stripped line text, representation for logs). Skip empty lines.
    """
    i = 0
    for line in instream:
        line = line.strip()
        if line:
            i += 1
            yield (i, line, line)
            if i % REPORT_CHUNKS == 0:
                logging.info('Read %d queries', i)


def parse_pcap(pcap_file):
    """
    Filters dns query packets from pcap_file
    Yield (packet number, packet as wire, representation for logs)
    """
    i = 0
    pcap_file = dpkt.pcap.Reader(pcap_file)
    for ts, wire in pcap_file:
        i += 1
        yield (i, wire, '')


def wrk_process_line(args: Tuple[int, str, str]) -> Tuple[bytes, bytes]:
    """
    Worker: parse input line, creates a packet in binary format

    Skips over empty lines, raises for malformed inputs.
    """
    qid, line, log_repr = args

    try:
        wire = wire_from_text(line)
    except (ValueError, struct.error, dns.exception.DNSException) as ex:
        logging.error('Invalid query "%s": %s (skipping query ID %d)', line, ex, qid)
        return
    wrk_process_wire_packet(qid, wire, line)


def wrk_process_packet(args: Tuple[int, bytes, str]):
    """
    Worker: convert packet from pcap to binary data
    """
    qid, wire, log_repr = args
    wrk_process_wire_packet(qid, wire, log_repr)


def wrk_process_wire_packet(qid: int, wire_packet: bytes, log_repr: str):
    """
    Worker: Check if given packet is blacklisted and save it into lmdb db

    :arg qid number of packet
    :arg wire_packet packet in binary data
    :arg log_repr representation of packet for logs
    """
    if not blacklist.is_blacklisted(wire_packet):
        wrk_lmdb_write(qid, wire_packet)
    else:
        logging.debug('Query "%s" blacklisted (skipping query ID %d)',
                      log_repr if log_repr else repr(blacklist.extract_packet(wire_packet)),
                      qid)


def int_or_fromtext(value, fromtext):
    try:
        return int(value)
    except ValueError:
        return fromtext(value)


def wire_from_text(text):
    """
    Convert line from <qname> <RR type> to DNS query in IN class.

    Returns: DNS packet in binary form
    Raises: ValueError or dns.exception.Exception on invalid input
    """
    qname, qtype = text.rsplit(None, 1)
    qname = dns.name.from_text(qname)
    qtype = int_or_fromtext(qtype, dns.rdatatype.from_text)
    msg = dns.message.make_query(qname, qtype, dns.rdataclass.IN,
                                 want_dnssec=True, payload=4096)
    return msg.to_wire()


def wrk_lmdb_init(envdir):
    """
    Worker: initialize LMDB env and open 'queries' database
    """
    global env
    global db

    config = dbhelper.env_open.copy()
    config.update({
        'path': envdir,
        'sync': False,  # unsafe but fast
        'writemap': True  # we do not care, this is a new database
    })
    env = lmdb.Environment(**config)
    db = env.open_db(key=b'queries', **dbhelper.db_open)


def wrk_lmdb_write(qid: int, wire: bytes):
    """
    Worker: write query wire format into database
    """
    global env
    global db

    key = dbhelper.qid2key(qid)
    with env.begin(db, write=True) as txn:
        txn.put(key, wire)


def main():
    logging.basicConfig(format='%(levelname)s %(message)s', level=logging.DEBUG)
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description='Convert queries data from standard input and store '
                    'wire format into LMDB "queries" DB.')

    parser.add_argument('envpath', type=str, help='path where to create LMDB environment')
    parser.add_argument('-f', '--in-format', type=str, choices=['text', 'pcap'], default='text',
                        help='define format for input data, default value is text\n'
                             'Expected input for "text" is: "<qname> <RR type>", '
                             'one query per line.\n'
                             'Expected input for "pcap" is content of the pcap file.')
    parser.add_argument('--pcap-file', type=argparse.FileType('rb'))
    args = parser.parse_args()

    if args.in_format == 'text' and args.pcap_file:
        logging.critical("Argument --pcap-file can be use only in combination with -f pcap")
        sys.exit(1)
    if args.in_format == 'pcap' and not args.pcap_file:
        logging.critical("Missing path to pcap file, use argument --pcap-file")
        sys.exit(1)
    if dbhelper.db_exists(args.envpath, dbhelper.QUERIES_DB_NAME):
        logging.critical(
            'LMDB environment "%s" already contains DB %s! '
            'Overwritting it would invalidate data in the environment, '
            'terminating.',
            args.envpath, dbhelper.QUERIES_DB_NAME)
        sys.exit(1)
    with pool.Pool(initializer=wrk_lmdb_init, initargs=(args.envpath,)) as workers:
        if args.in_format == 'text':
            data_stream = read_lines(sys.stdin)
            method = wrk_process_line
        elif args.in_format == 'pcap':
            data_stream = parse_pcap(args.pcap_file)
            method = wrk_process_packet
        else:
            logging.error('unknown in-format, use "text" or "pcap"')
            sys.exit(1)
        for _ in workers.imap_unordered(method, data_stream, chunksize=1000):
            pass


if __name__ == '__main__':
    main()
