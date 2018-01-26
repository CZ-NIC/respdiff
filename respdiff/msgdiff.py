#!/usr/bin/env python3

import argparse
from functools import partial
import logging
import multiprocessing.pool as pool
import pickle
from typing import Dict

import dns.message
import dns.exception

import cfg
import dataformat
from dbhelper import LMDB


lmdb = None


class DataMismatch(Exception):
    def __init__(self, exp_val, got_val):
        super(DataMismatch, self).__init__(exp_val, got_val)
        self.exp_val = exp_val
        self.got_val = got_val

    def __str__(self):
        return 'expected "{0.exp_val}" got "{0.got_val}"'.format(self)

    def __eq__(self, other):
        return (isinstance(other, DataMismatch)
                and self.exp_val == other.exp_val
                and self.got_val == other.got_val)

    def __ne__(self, other):
        return not self.__eq__(other)


def compare_val(exp_val, got_val):
    """ Compare values, throw exception if different. """
    if exp_val != got_val:
        raise DataMismatch(exp_val, got_val)
    return True


def compare_rrs(expected, got):
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


def compare_rrs_types(exp_val, got_val, skip_rrsigs):
    """sets of RR types in both sections must match"""
    def rr_ordering_key(rrset):
        if rrset.covers:
            return (rrset.covers, 1)  # RRSIGs go to the end of RRtype list
        return (rrset.rdtype, 0)

    def key_to_text(rrtype, rrsig):
        if not rrsig:
            return dns.rdatatype.to_text(rrtype)
        return 'RRSIG(%s)' % dns.rdatatype.to_text(rrtype)

    if skip_rrsigs:
        exp_val = (rrset for rrset in exp_val
                   if rrset.rdtype != dns.rdatatype.RRSIG)
        got_val = (rrset for rrset in got_val
                   if rrset.rdtype != dns.rdatatype.RRSIG)

    exp_types = frozenset(rr_ordering_key(rrset) for rrset in exp_val)
    got_types = frozenset(rr_ordering_key(rrset) for rrset in got_val)
    if exp_types != got_types:
        exp_types = tuple(key_to_text(*i) for i in sorted(exp_types))
        got_types = tuple(key_to_text(*i) for i in sorted(got_types))
        raise DataMismatch(exp_types, got_types)


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
        return compare_rrs_types(exp_msg.answer, got_msg.answer, skip_rrsigs=True)
    elif code == 'answerrrsigs':
        return compare_rrs_types(exp_msg.answer, got_msg.answer, skip_rrsigs=False)
    elif code == 'authority':
        return compare_rrs(exp_msg.authority, got_msg.authority)
    elif code == 'additional':
        return compare_rrs(exp_msg.additional, got_msg.additional)
    elif code == 'edns':
        if got_msg.edns != exp_msg.edns:
            raise DataMismatch(exp_msg.edns, got_msg.edns)
        if got_msg.payload != exp_msg.payload:
            raise DataMismatch(exp_msg.payload, got_msg.payload)
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
                    raise DataMismatch(None, opt.data)
                if opt == nsid_opt:
                    return True
                else:
                    raise DataMismatch(nsid_opt.data, opt.data)
        if nsid_opt:
            raise DataMismatch(nsid_opt.data, None)
    else:
        raise NotImplementedError('unknown match request "%s"' % code)


def match(expected, got, match_fields):
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


def decode_wire_dict(wire_dict: Dict[str, dataformat.Reply]) \
        -> Dict[str, dns.message.Message]:
    answers = {}  # type: Dict[str, dns.message.Message]
    for k, v in wire_dict.items():
        # decode bytes to dns.message objects
        # convert from wire format to DNS message object
        if v.wire is None:  # query timed out
            answers[k] = None
            continue
        try:
            answers[k] = dns.message.from_wire(v.wire)
        except Exception:
            # answers[k] = ex  # decoding failed, record it!
            continue
    return answers


def read_answers_lmdb(qid):
    adb = lmdb.get_db(LMDB.ANSWERS)
    with lmdb.env.begin(adb) as txn:
        blob = txn.get(qid)
    assert blob
    wire_dict = pickle.loads(blob)
    return decode_wire_dict(wire_dict)


def diff_pair(answers, criteria, name1, name2):
    """
    Returns: sequence of (field, DataMismatch())
    """
    yield from match(answers[name1], answers[name2], criteria)


def transitive_equality(answers, criteria, resolvers):
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


def compare(answers, criteria, target):
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


def main():
    global lmdb

    logging.basicConfig(format='%(levelname)s %(message)s', level=logging.DEBUG)
    parser = argparse.ArgumentParser(
        description='compute diff from answers stored in LMDB and write diffs to LMDB')
    parser.add_argument('-c', '--config', default='respdiff.cfg', dest='cfgpath',
                        help='config file (default: respdiff.cfg)')
    parser.add_argument('envdir', type=str,
                        help='LMDB environment to read answers from and to write diffs to')
    args = parser.parse_args()
    config = cfg.read_cfg(args.cfgpath)

    criteria = config['diff']['criteria']
    target = config['diff']['target']

    with LMDB(args.envdir) as lmdb_:
        lmdb = lmdb_
        lmdb.open_db(LMDB.ANSWERS)
        lmdb.open_db(LMDB.DIFFS, create=True, drop=True)
        qid_stream = lmdb.key_stream(LMDB.ANSWERS)
        func = partial(compare_lmdb_wrapper, criteria, target)
        with pool.Pool() as p:
            for _ in p.imap_unordered(func, qid_stream, chunksize=10):
                pass


if __name__ == '__main__':
    main()
