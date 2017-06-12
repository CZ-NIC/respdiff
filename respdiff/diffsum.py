import collections
import pickle
from pprint import pprint
import sys

import dns.rdatatype
import lmdb

import dbhelper
from msgdiff import DataMismatch  # needed for unpickling

def process_diff(field_weights, field_stats, question, diff):
    found = False
    for field in field_weights:
        if field in diff:
            significant_field = field
            break
    assert significant_field  # field must be in field_weights
    if significant_field == 'answer':
        return

    field_mismatches = field_stats.setdefault(field, {})
    mismatch = diff[significant_field]
    mismatch_key = (mismatch.exp_val, mismatch.got_val)
    mismatch_counter = field_mismatches.setdefault(mismatch_key, collections.Counter())
    mismatch_counter[question] += 1


def process_results(field_weights, diff_generator):
    """
    field_stats { field: value_stats { (exp, got): Counter(queries) } }
    """
    global_stats = {
        'others_disagree': 0,
        'target_disagrees': 0,
        }
    field_stats = {}

    #print('diffs = {')
    for qid, question, others_agree, target_diff in diff_generator:
        #print(qid, others_agree, target_diff)
        if not others_agree:
            global_stats['others_disagree'] += 1
            continue

        if not target_diff:  # everybody agreed, nothing to count
            continue

        #print('(%s, %s): ' % (qid, question))
        #print(target_diff, ',')

        global_stats['target_disagrees'] += 1
        process_diff(field_weights, field_stats, question, target_diff)

    #print('}')
    return global_stats, field_stats

def combine_stats(counters):
    field_mismatch_sums = {}
    for field in counters:
        field_mismatch_sums[field] = collections.Counter(
                {mismatch: sum(counter.values())
                 for mismatch, counter in counters[field].items()})

    field_sums = collections.Counter(
        {field: sum(counter.values())
         for field, counter in field_mismatch_sums.items()})
    return field_sums, field_mismatch_sums

def mismatch2str(mismatch):
    if not isinstance(mismatch[0], str):
        return (' '.join(mismatch[0]), ' '.join(mismatch[1]))
    else:
        return mismatch

def maxlen(iterable):
    return max(len(str(it)) for it in iterable)

def print_results(gstats, field_weights, counters, n=10):
    # global stats
    field_sums, field_mismatch_sums = combine_stats(counters)

    maxcntlen = maxlen(gstats.values())
    print('== Global statistics')
    print('queries            {:{}}'.format(gstats['queries'], maxcntlen))
    print('answers            {:{}}    {:6.2f} % of queries'.format(
        gstats['answers'], maxcntlen, float(100)*gstats['answers']/gstats['queries']))

    others_agree = gstats['answers'] - gstats['others_disagree']
    print('others agree       {:{}}    {:6.2f} % of answers (ignoring {:.2f} % of answers)'.format(
        others_agree, maxcntlen,
        100.0*others_agree/gstats['answers'],
        100.0*gstats['others_disagree']/gstats['answers']))
    target_disagrees = gstats['target_disagrees']
    print('target diagrees    {:{}}    {:6.2f} % of matching answers from others'.format(
        gstats['target_disagrees'], maxcntlen,
        100.0*gstats['target_disagrees']/gstats['answers']))

    print('')
    # print('== Field statistics: field - count - % of mismatches')
    maxnamelen = maxlen(field_sums.keys())
    maxcntlen = maxlen(field_sums.values())
    print('== {:{}}    {:{}}    {}'.format(
        'Field', maxnamelen - 3 - (len('count') - maxcntlen),
        'count', maxcntlen,
        '% of mismatches'))

    for field, n in (field_sums.most_common()):
        print('{:{}}    {:{}}     {:3.0f} %'.format(
            field, maxnamelen,
            n, maxcntlen,
            100.0*n/target_disagrees))

    for field in field_weights:
        if not field in field_mismatch_sums:
            continue
        print('')
        print('== Field "%s" mismatch statistics' % field)
        maxvallen = max((max(len(str(mismatch2str(mism)[0])), len(str(mismatch2str(mism)[1])))
                        for mism in field_mismatch_sums[field].keys()))
        maxcntlen = maxlen(field_mismatch_sums[field].values())
        print('{:{}}  !=  {:{}}    {:{}}    {}'.format(
            'Expected', maxvallen,
            'Got', maxvallen - (len('count') - maxcntlen),
            'count', maxcntlen,
            '% of mismatches'
            ))
        for mismatch, n in (field_mismatch_sums[field].most_common()):
            mismatch = mismatch2str(mismatch)
            print('{:{}}  !=  {:{}}    {:{}}    {:3.0f} %'.format(
                str(mismatch[0]), maxvallen,
                str(mismatch[1]), maxvallen,
                n, maxcntlen,
                100.0*n/target_disagrees))

    for field in field_weights:
        if not field in counters:
            continue
        for mismatch, n in (field_mismatch_sums[field].most_common(n)):
            print('')
            print('== Field "%s" mismatch %s query details' % (field, mismatch))
            counter = counters[field][mismatch]
            print_field_queries(field, counter, n)


def print_field_queries(field, counter, n):
    #print('queries leading to mismatch in field "%s":' % field)
    for query, count in counter.most_common(n):
        qname, qtype = query
        qtype = dns.rdatatype.to_text(qtype)
        print("%s %s\t\t%s mismatches" % (qname, qtype, count))

def open_db(envdir):
    config = dbhelper.env_open.copy()
    config.update({
        'path': envdir,
        'readonly': False,
        'create': False
        })
    lenv = lmdb.Environment(**config)
    qdb = lenv.open_db(key=b'queries', create=False, **dbhelper.db_open)
    adb = lenv.open_db(key=b'answers', create=False, **dbhelper.db_open)
    ddb = lenv.open_db(key=b'diffs', create=False, **dbhelper.db_open)
    return lenv, qdb, adb, ddb

def read_diffs_lmdb(levn, qdb, ddb):
    with levn.begin() as txn:
        with txn.cursor(ddb) as diffcur:
            for qid, diffblob in diffcur:
                others_agree, diff = pickle.loads(diffblob)
                if others_agree:
                    qwire = txn.get(qid, db=qdb)
                    qmsg = dns.message.from_wire(qwire)
                    question = (qmsg.question[0].name, qmsg.question[0].rdtype)
                else:
                    question = None
                yield (qid, question, others_agree, diff)

def main():
    lenv, qdb, adb, ddb = open_db(sys.argv[1])
    diff_stream = read_diffs_lmdb(lenv, qdb, ddb)
    field_weights = ['opcode', 'qcase', 'qtype', 'rcode', 'flags', 'answertypes', 'answerrrsigs', 'answer', 'authority', 'additional', 'edns']
    global_stats, field_stats = process_results(field_weights, diff_stream)
    with lenv.begin() as txn:
        global_stats['queries'] = txn.stat(qdb)['entries']
        global_stats['answers'] = txn.stat(adb)['entries']
    #pprint(field_stats)
    print_results(global_stats, field_weights, field_stats)

if __name__ == '__main__':
    main()
