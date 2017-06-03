from IPython.core.debugger import Tracer

import collections
import cProfile
import json
import pickle
from pprint import pprint
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


import itertools
import multiprocessing
import multiprocessing.pool as pool
import os

def find_querydirs(workdir):
    #i = 0
    for root, dirs, files in os.walk(workdir):
        dirs.sort()
        if not 'q.dns' in files:
            continue
        #i += 1
        #if i == 10000:
        #    return
        #print('yield %s' % root)
        yield root

def find_answer_qids(lenv, db):
    with lenv.begin(db) as txn:
        with txn.cursor(db) as cur:
            cont = cur.first()
            while cont:
                yield cur.key()
                cont = cur.next()

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
            try:
                answers[k] = dns.message.from_wire(v)
            except Exception as ex:
                #answers[k] = ex  # decoding failed, record it!
                continue
        return answers


def read_answers(workdir):
    answers = {}
    for filename in os.listdir(workdir):
        if filename == 'q.dns':
            continue
        #if filename == 'bind.dns':
        #    continue
        if not filename.endswith('.dns'):
            continue
        name = filename[:-4]
        filename = os.path.join(workdir, filename)
        with open(filename, 'rb') as msgfile:
            msg = dns.message.from_wire(msgfile.read())
        answers[name] = msg
    return answers

import struct
def read_answer_file(filename):
    with open(filename, 'rb') as af:
        binary = af.read()
    gidx = 0
    while gidx < len(binary):
        # set length
        set_len, *_ = struct.unpack('H', binary[gidx:gidx+2])
        gidx += 2
        set_binary = binary[gidx:gidx+set_len]
        gidx += set_len

        sidx = 0
        answers = {}
        while sidx < set_len:


            name, wire_len = struct.unpack('10p H', set_binary[sidx:sidx+12])
            sidx += 12
            name = name.decode('ascii')
            #msg = dns.message.from_wire(set_binary[sidx:sidx+wire_len])
            msg = set_binary[sidx:sidx+wire_len]
            sidx += wire_len
            answers[name] = msg
        yield answers


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
    #print('compare: %s %s %s' %(target, workdir, criteria))
    #answers = read_answers(workdir)
    # convert from wire format to DNS message object
    answers = read_answers_lmdb(lenv, answers_db, qid)
    others = list(answers.keys())
    try:
        others.remove(target)
    except ValueError:
        return (None, None, False, None)  # HACK, target did not reply
    #qid = str(answers[target].question[0])
    #qid = (workdir, answers[target].question[0].name, answers[target].question[0].rdtype)
    if len(others) <= 1:
        return (qid, None, False, None)  # HACK, not enough targets to compare
    random_other = others[0]

    assert len(others) >= 2
    # do others agree on the answer?
    others_agree = transitive_equality(answers, criteria, others)
    if not others_agree:
        return (qid, None, False, None)

    target_diffs = dict(diff_pair(answers, criteria, random_other, target))
    qs = answers[target].question[0]
    question = (qs.name, qs.rdtype)
    return (qid, question, others_agree, target_diffs)
    #target_agree = not any(target_diffs.values())
        #if not target_agree:
        #    print('target:')
        #    pprint(target_diffs)

    #if not all([target_agree, others_agree]):
        #write_txt(workdir, answers)
        #print('target agree %s, others agree %s' % (target_agree, others_agree))
#    for a, b in other_pairs:
#        diff = match(answers[a], answers[b], criteria)
#        print('diff %s ? %s: %s' % (a, b, diff))

def write_txt(workdir, answers):
    # target name goes first
    for name, answer in answers.items():
        path = os.path.join(workdir, '%s.txt' % name)
        with open(path, 'w') as txtfile:
            txtfile.write(str(answer))


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
        'create': False
        })
    lenv = lmdb.Environment(**config)
    answers_db = lenv.open_db(key=b'answers', create=False, **dbhelper.db_open)

    i = 0
    #prof = cProfile.Profile()
    #prof.enable()

    criteria = criteria_arg
    target = target_arg
    #print('criteria: %s target: %s' % (criteria, target))

def compare_wrapper(qid):
    global criteria
    global target
    #global result
    global i
    #global prof
    #return compare(target, workdir, criteria)
    result = compare(target, qid, criteria)
    #i += 1
    #if i == 10000:
    #    prof.disable()
    #    prof.dump_stats('prof%s.prof' % multiprocessing.current_process().name)
    #prof.runctx('global result; result = compare(target, workdir, criteria)', globals(), locals(), 'prof%s.prof' % multiprocessing.current_process().name)
    return result

def process_results(diff_generator):
    stats = {
        'queries': 0,
        'others_disagree': 0,
        'target_disagrees': 0,
        'diff_field_count': collections.Counter()
        }
    uniq = {}
    queries = collections.Counter()

    for qid, question, others_agree, target_diff in diff_generator:
        stats['queries'] += 1
        #print(qid, others_agree, target_diff)
        if not others_agree:
            stats['others_disagree'] += 1
            continue

        if target_diff:
            stats['target_disagrees'] += 1
            #print('("%s", "%s", "%s"): ' % qid)
            print('(%s, %s): ' % (qid, question))
            pprint(target_diff)
            print(',')
            diff_fields = list(target_diff.keys())
            stats['diff_field_count'].update(diff_fields)
            for field, value in target_diff.items():
                if field == 'answer':
                    continue
                queries.update([question])
                #print(type(question))
                #print(question)
                uniq.setdefault(field, collections.Counter()).update([value])

    print('}')
    stats['diff_field_count'] = dict(stats['diff_field_count'])
    print('stats = ')
    pprint(stats)
    print('uniq = ')
    #for field in uniq:
    #    uniq[field] = collections.OrderedDict(uniq[field].most_common(100))
    pprint(uniq)
    print('most common mismatches (not counting answer section):')
    for query, count in queries.most_common(100):
        qname, qtype = query
        qtype = dns.rdatatype.to_text(qtype)
        print("%s %s: %s mismatches" % (qname, qtype, count))
    #pprint(collections.OrderedDict(queries.most_common(100)))


def main():
    target = 'kresd'
    ccriteria = ['opcode', 'rcode', 'flags', 'question', 'qname', 'qtype', 'answer']  #'authority', 'additional', 'edns']
#ccriteria = ['opcode', 'rcode', 'flags', 'question', 'qname', 'qtype', 'answer', 'authority', 'additional', 'edns', 'nsid']
    #answers_stream = itertools.islice(read_answer_file('/tmp/all.dns2'), 100000)
    #answers_stream = itertools.islice(find_querydirs(sys.argv[1]), 90140, 90141)
    #answers_stream = itertools.islice(find_querydirs(sys.argv[1]), 300000)
    #answers_stream = find_querydirs(sys.argv[1])
    #for a in answers_stream:
    #    print(a)
    #answers_stream = itertools.islice(find_querydirs(sys.argv[1]), 300000)


    config = dbhelper.env_open.copy()
    config.update({
        'path': sys.argv[1],
        'readonly': True,
        'create': False
        })
    lenv = lmdb.Environment(**config)
    db = lenv.open_db(key=b'answers', create=False, **dbhelper.db_open)

    qid_stream = dbhelper.key_stream(lenv, db)
    #qid_stream = itertools.islice(find_answer_qids(lenv, db), 10000)
    print('diffs = {')

    serial = False
    if serial:
        worker_init(ccriteria, target)
        process_results(map(compare_wrapper, qid_stream))
    else:

        with pool.Pool(
                #processes=10,
                initializer=worker_init,
                initargs=(ccriteria, target)
            ) as p:
            process_results(p.imap_unordered(compare_wrapper, qid_stream, chunksize=10))

if __name__ == '__main__':
    main()
