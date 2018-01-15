#!/usr/bin/env python3

import argparse
import logging
import itertools
import multiprocessing
import multiprocessing.pool as pool
import os
import pickle
import sys

import dns.message
import dns.exception
import lmdb

import cfg
import dataformat
import dbhelper


class DataMismatch(Exception):
    def __init__(self, exp_val, got_val):
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
        else:
            return (rrset.rdtype, 0)

    def key_to_text(rrtype, rrsig):
        if not rrsig:
            return dns.rdatatype.to_text(rrtype)
        else:
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


def match_part(exp_msg, got_msg, code):
    """ Compare scripted reply to given message using single criteria. """
    if code == 'opcode':
        return compare_val(exp_msg.opcode(), got_msg.opcode())
    elif code == 'qtype':
        if len(exp_msg.question) == 0:
            return True
        return compare_val(exp_msg.question[0].rdtype, got_msg.question[0].rdtype)
    elif code == 'qname':
        if len(exp_msg.question) == 0:
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
    for code in match_fields:
        try:
            res = match_part(expected, got, code)
        except DataMismatch as ex:
            yield (code, ex)


def decode_wire_dict(wire_dict):
    assert isinstance(wire_dict, dict)
    answers = {}
    for k, v in wire_dict.items():
        # decode bytes to dns.message objects
        # if isinstance(v, bytes):
        # convert from wire format to DNS message object
        try:
            answers[k] = dns.message.from_wire(v)
        except Exception as ex:
            # answers[k] = ex  # decoding failed, record it!
            continue
    return answers


def read_answers_lmdb(lenv, db, qid):
    with lenv.begin(db) as txn:
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
    if len(others) == 0:
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


def worker_init(envdir_arg, criteria_arg, target_arg):
    global envdir
    global criteria
    global target

    global lenv
    global answers_db
    global diffs_db
    config = dbhelper.env_open.copy()
    config.update({
        'path': envdir_arg,
        'readonly': False,
        'create': False,
        'writemap': True,
        'sync': False
    })
    lenv = lmdb.Environment(**config)
    answers_db = lenv.open_db(key=dbhelper.ANSWERS_DB_NAME, create=False, **dbhelper.db_open)
    diffs_db = lenv.open_db(key=dbhelper.DIFFS_DB_NAME, create=True, **dbhelper.db_open)

    criteria = criteria_arg
    target = target_arg
    envdir = envdir_arg


def compare_lmdb_wrapper(qid):
    global lenv
    global diffs_db
    global criteria
    global target
    answers = read_answers_lmdb(lenv, answers_db, qid)
    others_agree, target_diffs = compare(answers, criteria, target)
    if others_agree and not target_diffs:
        return  # all agreed, nothing to write
    blob = pickle.dumps((others_agree, target_diffs))
    with lenv.begin(diffs_db, write=True) as txn:
        txn.put(qid, blob)


def main():
    logging.basicConfig(format='%(levelname)s %(message)s', level=logging.DEBUG)
    parser = argparse.ArgumentParser(
        description='compute diff from answers stored in LMDB and write diffs to LMDB')
    parser.add_argument('-c', '--config', default='respdiff.cfg', dest='cfgpath',
                        help='config file (default: respdiff.cfg)')
    parser.add_argument('envdir', type=str,
                        help='LMDB environment to read answers from and to write diffs to')
    args = parser.parse_args()
    config = cfg.read_cfg(args.cfgpath)

    envconfig = dbhelper.env_open.copy()
    envconfig.update({
        'path': args.envdir,
        'readonly': False,
        'create': False
    })
    lenv = lmdb.Environment(**envconfig)

    try:
        db = lenv.open_db(key=dbhelper.ANSWERS_DB_NAME, create=False, **dbhelper.db_open)
    except lmdb.NotFoundError:
        logging.critical('LMDB does not contain DNS answers in DB %s, terminating.',
                         dbhelper.ANSWERS_DB_NAME)
        sys.exit(1)

    try:  # drop diffs DB if it exists, it can be re-generated at will
        diffs_db = lenv.open_db(key=dbhelper.DIFFS_DB_NAME, create=False, **dbhelper.db_open)
        with lenv.begin(write=True) as txn:
            txn.drop(diffs_db)
    except lmdb.NotFoundError:
        pass

    qid_stream = dbhelper.key_stream(lenv, db)
    with pool.Pool(
        initializer=worker_init,
        initargs=(args.envdir, config['diff']['criteria'], config['diff']['target'])
    ) as p:
        for i in p.imap_unordered(compare_lmdb_wrapper, qid_stream, chunksize=10):
            pass


if __name__ == '__main__':
    main()
