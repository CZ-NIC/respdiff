from collections import Counter
import logging
from typing import Callable, Iterable, Iterator, Sequence, Tuple

import dns.message
import dns.rdatatype

from .database import LMDB, qid2key
from .typing import QID, WireFormat


def get_query_iterator(
            lmdb_,
            qids: Iterable[QID]
        ) -> Iterator[Tuple[QID, WireFormat]]:
    qdb = lmdb_.get_db(LMDB.QUERIES)
    with lmdb_.env.begin(qdb) as txn:
        for qid in qids:
            key = qid2key(qid)
            qwire = txn.get(key)
            yield qid, qwire


def qwire_to_qname(qwire: WireFormat) -> str:
    try:
        qmsg = dns.message.from_wire(qwire)
    except dns.exception.DNSException as exc:
        raise ValueError('unable to parse qname from wire format') from exc
    if not qmsg.question:
        raise ValueError('no qname in wire format')
    return qmsg.question[0].name


def qwire_to_qname_qtype(qwire: WireFormat) -> str:
    """Get text representation of DNS wire format query"""
    try:
        qmsg = dns.message.from_wire(qwire)
    except dns.exception.DNSException as exc:
        raise ValueError('unable to parse qname from wire format') from exc
    if not qmsg.question:
        raise ValueError('no qname in wire format')
    return '{} {}'.format(
        qmsg.question[0].name,
        dns.rdatatype.to_text(qmsg.question[0].rdtype))


def qwire_to_msgid_qname_qtype(qwire: WireFormat) -> str:
    """Get text representation of DNS wire format query"""
    try:
        qmsg = dns.message.from_wire(qwire)
    except dns.exception.DNSException as exc:
        raise ValueError('unable to parse qname from wire format') from exc
    if not qmsg.question:
        raise ValueError('no qname in wire format')
    return '[{:05d}] {} {}'.format(
        qmsg.id,
        qmsg.question[0].name,
        dns.rdatatype.to_text(qmsg.question[0].rdtype))


def convert_queries(
            query_iterator: Iterator[Tuple[QID, WireFormat]],
            qwire_to_text_func: Callable[[WireFormat], str] = qwire_to_qname_qtype
        ) -> Counter:
    qcounter = Counter()  # type: Counter
    for qid, qwire in query_iterator:
        try:
            text = qwire_to_text_func(qwire)
        except ValueError as exc:
            logging.debug('Omitting QID %d: %s', qid, exc)
        else:
            qcounter[text] += 1
    return qcounter


def get_printable_queries_format(
            queries_mismatch: Counter,
            queries_all: Counter = None,  # all queries (needed for comparison with ref)
            ref_queries_mismatch: Counter = None,  # ref queries for the same mismatch
            ref_queries_all: Counter = None  # ref queries from all mismatches
        ) -> Sequence[Tuple[str, int, str]]:
    def get_query_diff(query: str) -> str:
        if (ref_queries_mismatch is None
                or ref_queries_all is None
                or queries_all is None):
            return ' '  # no reference to compare to
        if query in queries_mismatch and query not in ref_queries_all:
            return '+'  # previously unseen query has appeared
        if query in ref_queries_mismatch and query not in queries_all:
            return '-'  # query no longer appears in any mismatch category
        return ' '  # no change, or query has moved to a different mismatch category

    query_set = set(queries_mismatch.keys())
    if ref_queries_mismatch is not None:
        assert ref_queries_all is not None
        assert queries_all is not None
        # ref_mismach has to be include to be able to display '-' queries
        query_set.update(ref_queries_mismatch.keys())

    queries = []
    for query in query_set:
        diff = get_query_diff(query)
        count = queries_mismatch[query]
        if diff == ' ' and count == 0:
            continue  # omit queries that just moved between categories
        if diff == '-':
            assert ref_queries_mismatch is not None
            count = ref_queries_mismatch[query]  # show how many cases were removed
        queries.append((diff, count, query))
    return queries
