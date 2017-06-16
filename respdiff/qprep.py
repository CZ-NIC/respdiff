import multiprocessing.pool as pool
import sys

import dns.message
import dns.rdatatype
import lmdb

import blacklist
import dbhelper


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
    msg = q_fromtext(line)
    if not blacklist.obj_blacklisted(msg):
        wrk_lmdb_write(qid, msg.to_wire())


def main():
    qstream = read_lines(sys.stdin)
    with pool.Pool(initializer=wrk_lmdb_init, initargs=(sys.argv[1],)) as workers:
        for _ in workers.imap_unordered(wrk_process_line, qstream, chunksize=1000):
            pass

if __name__ == '__main__':
    main()
