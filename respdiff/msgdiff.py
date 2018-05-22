#!/usr/bin/env python3

import argparse
from functools import partial
import logging
import multiprocessing.pool as pool
import pickle
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Tuple  # noqa

import dns.exception
import dns.message
from dns.rrset import RRset

import cli
from dataformat import (
    DataMismatch, DiffReport, Disagreements, DisagreementsCounter,
    FieldLabel, MismatchValue, QID)
from dbhelper import DNSReply, LMDB, key2qid
from sendrecv import ResolverID


lmdb = None


def compare_val(exp_val: MismatchValue, got_val: MismatchValue):
    """ Compare values, throw exception if different. """
    if exp_val != got_val:
        raise DataMismatch(str(exp_val), str(got_val))
    return True


def compare_rrs(expected: RRset, got: RRset):
    """ Compare lists of RR sets, throw exception if different. """
    for rr in expected:
        if rr not in got:
            raise DataMismatch(expected, got)
    for rr in got:
        if rr not in expected:
            raise DataMismatch(expected, got)
    if len(expected) != len(got):
        raise DataMismatch(expected, got)
    return True


def compare_rrs_types(exp_val: RRset, got_val: RRset, compare_rrsigs: bool):
    """sets of RR types in both sections must match"""
    def rr_ordering_key(rrset):
        return rrset.covers if compare_rrsigs else rrset.rdtype

    def key_to_text(rrtype):
        if not compare_rrsigs:
            return dns.rdatatype.to_text(rrtype)
        return 'RRSIG(%s)' % dns.rdatatype.to_text(rrtype)

    def filter_by_rrsig(seq, rrsig):
        for el in seq:
            el_rrsig = el.rdtype == dns.rdatatype.RRSIG
            if el_rrsig == rrsig:
                yield el

    exp_types = frozenset(rr_ordering_key(rrset)
                          for rrset in filter_by_rrsig(exp_val, compare_rrsigs))
    got_types = frozenset(rr_ordering_key(rrset)
                          for rrset in filter_by_rrsig(got_val, compare_rrsigs))
    if exp_types != got_types:
        raise DataMismatch(
            tuple(key_to_text(i) for i in sorted(exp_types)),
            tuple(key_to_text(i) for i in sorted(got_types)))


def match_part(exp_msg, got_msg, code):  # pylint: disable=inconsistent-return-statements
    """ Compare scripted reply to given message using single criteria. """
    if code == 'opcode':
        return compare_val(exp_msg.opcode(), got_msg.opcode())
    elif code == 'qtype':
        if not exp_msg.question:
            return True
        return compare_val(exp_msg.question[0].rdtype, got_msg.question[0].rdtype)
    elif code == 'qname':
        if not exp_msg.question:
            return True
        return compare_val(exp_msg.question[0].name, got_msg.question[0].name)
    elif code == 'qcase':
        return compare_val(got_msg.question[0].name.labels, exp_msg.question[0].name.labels)
    elif code == 'flags':
        return compare_val(dns.flags.to_text(exp_msg.flags), dns.flags.to_text(got_msg.flags))
    elif code == 'rcode':
        return compare_val(dns.rcode.to_text(exp_msg.rcode()), dns.rcode.to_text(got_msg.rcode()))
    elif code == 'question':
        return compare_rrs(exp_msg.question, got_msg.question)
    elif code == 'answer' or code == 'ttl':
        return compare_rrs(exp_msg.answer, got_msg.answer)
    elif code == 'answertypes':
        return compare_rrs_types(exp_msg.answer, got_msg.answer, compare_rrsigs=False)
    elif code == 'answerrrsigs':
        return compare_rrs_types(exp_msg.answer, got_msg.answer, compare_rrsigs=True)
    elif code == 'authority':
        return compare_rrs(exp_msg.authority, got_msg.authority)
    elif code == 'additional':
        return compare_rrs(exp_msg.additional, got_msg.additional)
    elif code == 'edns':
        if got_msg.edns != exp_msg.edns:
            raise DataMismatch(str(exp_msg.edns), str(got_msg.edns))
        if got_msg.payload != exp_msg.payload:
            raise DataMismatch(str(exp_msg.payload), str(got_msg.payload))
    elif code == 'nsid':
        nsid_opt = None
        for opt in exp_msg.options:
            if opt.otype == dns.edns.NSID:
                nsid_opt = opt
                break
        # Find matching NSID
        for opt in got_msg.options:
            if opt.otype == dns.edns.NSID:
                if not nsid_opt:
                    raise DataMismatch('', str(opt.data))
                if opt == nsid_opt:
                    return True
                else:
                    raise DataMismatch(str(nsid_opt.data), str(opt.data))
        if nsid_opt:
            raise DataMismatch(str(nsid_opt.data), '')
    else:
        raise NotImplementedError('unknown match request "%s"' % code)


def match(
            expected: dns.message.Message,
            got: dns.message.Message,
            match_fields: Sequence[FieldLabel]
        ) -> Iterator[Tuple[FieldLabel, DataMismatch]]:
    """ Compare scripted reply to given message based on match criteria. """
    if expected is None or got is None:
        if expected is not None:
            yield 'timeout', DataMismatch('answer', 'timeout')
        if got is not None:
            yield 'timeout', DataMismatch('timeout', 'answer')
        return  # don't attempt to match any other fields if one answer is timeout
    for code in match_fields:
        try:
            match_part(expected, got, code)
        except DataMismatch as ex:
            yield (code, ex)


def decode_replies(
            replies: Mapping[ResolverID, DNSReply]
        ) -> Mapping[ResolverID, dns.message.Message]:
    answers = {}  # type: Dict[ResolverID, dns.message.Message]
    for resolver, reply in replies.items():
        if reply.timeout:
            answers[resolver] = None
            continue
        try:
            answers[resolver] = dns.message.from_wire(reply.wire)
        except Exception as exc:
            logging.warning('Failed to decode DNS message from wire format: %s', exc)
            continue
    return answers


def read_answers_lmdb(qid: QID) -> Mapping[ResolverID, dns.message.Message]:
    if lmdb is None:
        raise RuntimeError("LMDB wasn't initialized!")
    adb = lmdb.get_db(LMDB.ANSWERS)
    with lmdb.env.begin(adb) as txn:
        replies_blob = txn.get(qid)
    assert replies_blob
    replies = pickle.loads(replies_blob)
    return decode_replies(replies)


def diff_pair(
            answers: Mapping[ResolverID, dns.message.Message],
            criteria: Sequence[FieldLabel],
            name1: ResolverID,
            name2: ResolverID
        ) -> Iterator[Tuple[FieldLabel, DataMismatch]]:
    yield from match(answers[name1], answers[name2], criteria)


def transitive_equality(
            answers: Mapping[ResolverID, dns.message.Message],
            criteria: Sequence[FieldLabel],
            resolvers: Sequence[ResolverID]
        ) -> bool:
    """
    Compare answers from all resolvers.
    Optimization is based on transitivity of equivalence relation.
    """
    assert len(resolvers) >= 2
    res_a = resolvers[0]  # compare all others to this resolver
    res_others = resolvers[1:]
    return all(map(
        lambda res_b: not any(diff_pair(answers, criteria, res_a, res_b)),
        res_others))


def compare(
            answers: Mapping[ResolverID, dns.message.Message],
            criteria: Sequence[FieldLabel],
            target: ResolverID
        ) -> Tuple[bool, Optional[Mapping[FieldLabel, DataMismatch]]]:
    others = list(answers.keys())
    try:
        others.remove(target)
    except ValueError:
        return (False, None)  # HACK, target did not reply
    if not others:
        return (False, None)  # HACK, not enough targets to compare
    random_other = others[0]

    if len(others) >= 2:
        # do others agree on the answer?
        others_agree = transitive_equality(answers, criteria, others)
        if not others_agree:
            return (False, None)
    else:
        others_agree = True
    target_diffs = dict(diff_pair(answers, criteria, random_other, target))
    return (others_agree, target_diffs)


def compare_lmdb_wrapper(criteria, target, qid):
    answers = read_answers_lmdb(qid)
    others_agree, target_diffs = compare(answers, criteria, target)
    if others_agree and not target_diffs:
        return  # all agreed, nothing to write
    blob = pickle.dumps((others_agree, target_diffs))
    ddb = lmdb.get_db(LMDB.DIFFS)
    with lmdb.env.begin(ddb, write=True) as txn:
        txn.put(qid, blob)


def export_json(filename):
    report = DiffReport.from_json(filename)
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

    report.export_json(filename)


def main():
    global lmdb

    cli.setup_logging()
    parser = argparse.ArgumentParser(
        description='compute diff from answers stored in LMDB and write diffs to LMDB')
    cli.add_arg_envdir(parser)
    cli.add_arg_config(parser)
    cli.add_arg_datafile(parser)

    args = parser.parse_args()
    datafile = cli.get_datafile(args)
    criteria = args.cfg['diff']['criteria']
    target = args.cfg['diff']['target']

    with LMDB(args.envdir, fast=True) as lmdb_:
        lmdb = lmdb_
        lmdb.open_db(LMDB.ANSWERS)
        lmdb.open_db(LMDB.DIFFS, create=True, drop=True)
        qid_stream = lmdb.key_stream(LMDB.ANSWERS)
        func = partial(compare_lmdb_wrapper, criteria, target)
        with pool.Pool() as p:
            for _ in p.imap_unordered(func, qid_stream, chunksize=10):
                pass
        export_json(datafile)


if __name__ == '__main__':
    main()
