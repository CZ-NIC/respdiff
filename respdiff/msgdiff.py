from IPython.core.debugger import Tracer

import cProfile

import itertools
import multiprocessing
import multiprocessing.pool as pool
import os
import pickle
import sys

import dns.message
import dns.exception
import lmdb

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
        return self.__eq__(other)

    def __hash__(self):
        try:
            return hash(self.exp_val) + hash(self.got_val)
        except TypeError:  # FIXME: unhashable types
            return 0

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
        #raise Exception("expected %s records but got %s records "
        #                "(a duplicate RR somewhere?)"
        #                % (len(expected), len(got)))
    return True

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
    #elif code == 'subdomain':
    #    if len(exp_msg.question) == 0:
    #        return True
    #    qname = dns.name.from_text(got_msg.question[0].name.to_text().lower())
    #    return compare_sub(exp_msg.question[0].name, qname)
    elif code == 'flags':
        return compare_val(dns.flags.to_text(exp_msg.flags), dns.flags.to_text(got_msg.flags))
    elif code == 'rcode':
        return compare_val(dns.rcode.to_text(exp_msg.rcode()), dns.rcode.to_text(got_msg.rcode()))
    elif code == 'question':
        return compare_rrs(exp_msg.question, got_msg.question)
    elif code == 'answer' or code == 'ttl':
        return compare_rrs(exp_msg.answer, got_msg.answer)
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


def read_answers_lmdb(lenv, db, qid):
    answers = {}
    with lenv.begin(db) as txn:
        blob = txn.get(qid)
        assert blob
        blob_dict = pickle.loads(blob)
        assert isinstance(blob_dict, dict)
        for k, v in blob_dict.items():
            # decode bytes to dns.message objects
            #if isinstance(v, bytes):
            # convert from wire format to DNS message object
            try:
                answers[k] = dns.message.from_wire(v)
            except Exception as ex:
                #answers[k] = ex  # decoding failed, record it!
                continue
        return answers


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


def compare(target, qid, criteria):
    global lenv
    global answers_db
    answers = read_answers_lmdb(lenv, answers_db, qid)
    others = list(answers.keys())
    try:
        others.remove(target)
    except ValueError:
        return (False, None)  # HACK, target did not reply
    if len(others) <= 1:
        return (False, None)  # HACK, not enough targets to compare
    random_other = others[0]

    assert len(others) >= 2
    # do others agree on the answer?
    others_agree = transitive_equality(answers, criteria, others)
    if not others_agree:
        return (False, None)

    target_diffs = dict(diff_pair(answers, criteria, random_other, target))
    return (others_agree, target_diffs)


def worker_init(criteria_arg, target_arg):
    global criteria
    global target
    global prof
    global i

    global lenv
    global answers_db
    global diffs_db
    config = dbhelper.env_open.copy()
    config.update({
        'path': sys.argv[1],
        'readonly': False,
        'create': False,
        'writemap': True,
        'sync': False
        })
    lenv = lmdb.Environment(**config)
    answers_db = lenv.open_db(key=b'answers', create=False, **dbhelper.db_open)
    diffs_db = lenv.open_db(key=b'diffs', create=True, **dbhelper.db_open)

    i = 0
    #prof = cProfile.Profile()
    #prof.enable()

    criteria = criteria_arg
    target = target_arg
    #print('criteria: %s target: %s' % (criteria, target))

def compare_lmdb_wrapper(qid):
    global lenv
    global diffs_db
    global criteria
    global target
    #global result
    global i
    #global prof
    #return compare(target, workdir, criteria)
    others_agree, target_diffs = compare(target, qid, criteria)
    if others_agree and not target_diffs:
        return  # all agreed, nothing to write
    blob = pickle.dumps((others_agree, target_diffs))
    with lenv.begin(diffs_db, write=True) as txn:
        txn.put(qid, blob)
    #i += 1
    #if i == 10000:
    #    prof.disable()
    #    prof.dump_stats('prof%s.prof' % multiprocessing.current_process().name)
    #prof.runctx('global result; result = compare(target, workdir, criteria)', globals(), locals(), 'prof%s.prof' % multiprocessing.current_process().name)


def main():
    target = 'kresd'
    ccriteria = ['opcode', 'rcode', 'flags', 'question', 'qname', 'qtype', 'answer']  #'authority', 'additional', 'edns']
#ccriteria = ['opcode', 'rcode', 'flags', 'question', 'qname', 'qtype', 'answer', 'authority', 'additional', 'edns', 'nsid']

    config = dbhelper.env_open.copy()
    config.update({
        'path': sys.argv[1],
        'readonly': False,
        'create': False
        })
    lenv = lmdb.Environment(**config)
    db = lenv.open_db(key=b'answers', create=False, **dbhelper.db_open)
    try:  # FIXME: drop database for now, debug only
        diffs_db = lenv.open_db(key=b'diffs', create=False, **dbhelper.db_open)
        with lenv.begin(write=True) as txn:
            txn.drop(diffs_db)
    except lmdb.NotFoundError:
        pass

    qid_stream = dbhelper.key_stream(lenv, db)
    #qid_stream = itertools.islice(find_answer_qids(lenv, db), 10000)

    serial = False
    if serial:
        worker_init(ccriteria, target)
        for i in map(compare_lmdb_wrapper, qid_stream):
            pass
    else:

        with pool.Pool(
                #processes=10,
                initializer=worker_init,
                initargs=(ccriteria, target)
            ) as p:
            for i in p.imap_unordered(compare_lmdb_wrapper, qid_stream, chunksize=10):
                pass

if __name__ == '__main__':
    main()
