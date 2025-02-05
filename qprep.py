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
    i = 1
    for line in instream:
        if i % REPORT_CHUNKS == 0:
            logging.info("Read %d lines", i)
        line = line.strip()
        if line:
            yield (i, line, line)
        i += 1


def extract_wire(packet: bytes) -> bytes:
    """
    Extract DNS message wire format from PCAP packet.
    UDP payload is passed as it was.
    TCP payload will have first two bytes removed (length prefix).
    Caller must verify if return value is a valid DNS message
    and decice what to do with invalid ones.
    """
    frame = dpkt.ethernet.Ethernet(packet)
    ip = frame.data
    transport = ip.data
    if isinstance(transport, dpkt.tcp.TCP):
        if len(transport.data) < 2:
            return transport.data
        wire = transport.data[2:]
    else:
        wire = transport.data
    return wire


def parse_pcap(pcap_file):
    """
    Filters dns query packets from pcap_file
    Yield (packet number, packet as wire, representation for logs)
    """
    i = 1
    pcap_file = dpkt.pcap.Reader(pcap_file)
    for _, frame in pcap_file:
        if i % REPORT_CHUNKS == 0:
            logging.info("Read %d frames", i)
        yield (i, frame, "frame no. {}".format(i))
        i += 1


def wrk_process_line(
    args: Tuple[int, str, str]
) -> Tuple[Optional[int], Optional[bytes]]:
    """
    Worker: parse input line, creates a packet in binary format

    Skips over malformed inputs.
    """
    qid, line, log_repr = args

    try:
        msg = msg_from_text(line)
        if blacklist.is_blacklisted(msg):
            logging.debug('Blacklisted query "%s", skipping QID %d', log_repr, qid)
            return None, None
        return qid, msg.to_wire()
    except (ValueError, struct.error, dns.exception.DNSException) as ex:
        logging.error(
            'Invalid query specification "%s": %s, skipping QID %d', line, ex, qid
        )
        return None, None


def wrk_process_frame(
    args: Tuple[int, bytes, str]
) -> Tuple[Optional[int], Optional[bytes]]:
    """
    Worker: convert packet from pcap to binary data
    """
    qid, frame, log_repr = args
    wire = extract_wire(frame)
    return wrk_process_wire_packet(qid, wire, log_repr)


def wrk_process_wire_packet(
    qid: int, wire_packet: bytes, log_repr: str
) -> Tuple[Optional[int], Optional[bytes]]:
    """
    Worker: Return packet's data if it's not blacklisted

    :arg qid number of packet
    :arg wire_packet packet in binary data
    :arg log_repr representation of packet for logs
    """
    try:
        msg = dns.message.from_wire(wire_packet)
    except dns.exception.DNSException:
        # pass invalid blobs to LMDB (for testing non-standard states)
        pass
    else:
        if blacklist.is_blacklisted(msg):
            logging.debug('Blacklisted query "%s", skipping QID %d', log_repr, qid)
            return None, None
    return qid, wire_packet


def int_or_fromtext(value, fromtext):
    try:
        return int(value)
    except ValueError:
        return fromtext(value)


def msg_from_text(text):
    """
    Convert line from <qname> <RR type> to DNS query in IN class.

    Returns: DNS packet in binary form
    Raises: ValueError or dns.exception.Exception on invalid input
    """
    try:
        qname, qtype = text.split()
    except ValueError as e:
        raise ValueError(
            "space is only allowed as separator between qname qtype"
        ) from e
    qname = dns.name.from_text(qname.encode("ascii"))
    qtype = int_or_fromtext(qtype, dns.rdatatype.from_text)
    msg = dns.message.make_query(
        qname, qtype, dns.rdataclass.IN, want_dnssec=True, payload=4096
    )
    return msg


def main():
    cli.setup_logging()
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description="Convert queries data from standard input and store "
        'wire format into LMDB "queries" DB.',
    )
    cli.add_arg_envdir(parser)
    parser.add_argument(
        "-f",
        "--in-format",
        type=str,
        choices=["text", "pcap"],
        default="text",
        help="define format for input data, default value is text\n"
        'Expected input for "text" is: "<qname> <RR type>", '
        "one query per line.\n"
        'Expected input for "pcap" is content of the pcap file.',
    )
    parser.add_argument("--pcap-file", type=argparse.FileType("rb"))

    args = parser.parse_args()

    if args.in_format == "text" and args.pcap_file:
        logging.critical(
            "Argument --pcap-file can be use only in combination with -f pcap"
        )
        sys.exit(1)
    if args.in_format == "pcap" and not args.pcap_file:
        logging.critical("Missing path to pcap file, use argument --pcap-file")
        sys.exit(1)

    with LMDB(args.envdir) as lmdb:
        qdb = lmdb.open_db(LMDB.QUERIES, create=True, check_notexists=True)
        txn = lmdb.env.begin(qdb, write=True)
        try:
            with pool.Pool(
                initializer=lambda: signal.signal(signal.SIGINT, signal.SIG_IGN)
            ) as workers:
                if args.in_format == "text":
                    data_stream = read_lines(sys.stdin)
                    method = wrk_process_line
                elif args.in_format == "pcap":
                    data_stream = parse_pcap(args.pcap_file)
                    method = wrk_process_frame
                else:
                    logging.error('unknown in-format, use "text" or "pcap"')
                    sys.exit(1)
                for qid, wire in workers.imap(method, data_stream, chunksize=1000):
                    if qid is not None:
                        key = qid2key(qid)
                        txn.put(key, wire)
        except KeyboardInterrupt:
            logging.info("SIGINT received, exiting...")
            sys.exit(130)
        except RuntimeError as err:
            logging.error(err)
            sys.exit(1)
        finally:
            # attempt to preserve data if something went wrong (or not)
            logging.debug("Comitting LMDB transaction...")
            txn.commit()


if __name__ == "__main__":
    main()
