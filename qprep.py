#!/usr/bin/env python3

import argparse
import logging
from multiprocessing import pool
import signal
import struct
import sys
from typing import Optional, Tuple

import dpkt
import dns.exception
import dns.message
import dns.rdatatype

from respdiff import blacklist, cli
from respdiff.database import LMDB, qid2key

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
    for _, wire in pcap_file:
        i += 1
        yield (i, wire, '')


def wrk_process_line(
            args: Tuple[int, str, str]
        ) -> Tuple[Optional[bytes], Optional[bytes]]:
    """
    Worker: parse input line, creates a packet in binary format

    Skips over empty lines, raises for malformed inputs.
    """
    qid, line, _ = args

    try:
        wire = wire_from_text(line)
    except (ValueError, struct.error, dns.exception.DNSException) as ex:
        logging.error('Invalid query "%s": %s (skipping query ID %d)', line, ex, qid)
        return None, None
    return wrk_process_wire_packet(qid, wire, line)


def wrk_process_packet(args: Tuple[int, bytes, str]):
    """
    Worker: convert packet from pcap to binary data
    """
    qid, wire, log_repr = args
    wrk_process_wire_packet(qid, wire, log_repr)


def wrk_process_wire_packet(
            qid: int,
            wire_packet: bytes,
            log_repr: str
        ) -> Tuple[Optional[bytes], Optional[bytes]]:
    """
    Worker: Return packet's data if it's not blacklisted

    :arg qid number of packet
    :arg wire_packet packet in binary data
    :arg log_repr representation of packet for logs
    """
    if not blacklist.is_blacklisted(wire_packet):
        key = qid2key(qid)
        return key, wire_packet

    logging.debug('Query "%s" blacklisted (skipping query ID %d)',
                  log_repr if log_repr else repr(blacklist.extract_packet(wire_packet)),
                  qid)
    return None, None


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
    qname = dns.name.from_text(qname.encode('ascii'))
    qtype = int_or_fromtext(qtype, dns.rdatatype.from_text)
    msg = dns.message.make_query(qname, qtype, dns.rdataclass.IN,
                                 want_dnssec=True, payload=4096)
    return msg.to_wire()


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description='Convert queries data from standard input and store '
                    'wire format into LMDB "queries" DB.')
    cli.add_arg_envdir(parser)
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

    with LMDB(args.envdir) as lmdb:
        qdb = lmdb.open_db(LMDB.QUERIES, create=True, check_notexists=True)
        txn = lmdb.env.begin(qdb, write=True)
        try:
            with pool.Pool(
                    initializer=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
                    ) as workers:
                if args.in_format == 'text':
                    data_stream = read_lines(sys.stdin)
                    method = wrk_process_line
                elif args.in_format == 'pcap':
                    data_stream = parse_pcap(args.pcap_file)
                    method = wrk_process_packet
                else:
                    logging.error('unknown in-format, use "text" or "pcap"')
                    sys.exit(1)
                for key, wire in workers.imap(method, data_stream, chunksize=1000):
                    if key is not None:
                        txn.put(key, wire)
        except KeyboardInterrupt as err:
            logging.info('SIGINT received, exiting...')
            sys.exit(130)
        except RuntimeError as err:
            logging.error(err)
            sys.exit(1)
        finally:
            # attempt to preserve data if something went wrong (or not)
            logging.debug('Comitting LMDB transaction...')
            txn.commit()


if __name__ == '__main__':
    main()
