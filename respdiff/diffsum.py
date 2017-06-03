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

def print_results(global_stats, field_weights, counters, n=10):
    # global stats
    field_sums, field_mismatch_sums = combine_stats(counters)

    print('== Global statistics')
    print('others diagree : %s' % (global_stats['others_disagree']))
    target_disagrees = global_stats['target_disagrees']
    print('target diagrees:', target_disagrees)

    print('')
    print('== Field statistics: field - count - % of mismatches')
    for field, n in (field_sums.most_common()):
        #print('%s\t%i\t%4.01f %%' % (field, n, float(n)/target_disagrees*100))
        print('%s\t%i' % (field, n))

    for field in field_weights:
        if not field in field_mismatch_sums:
            continue
        print('')
        print('== Field "%s" mismatch statistics' % field)
        for mismatch, n in (field_mismatch_sums[field].most_common()):
            print('%s\t%i' % (mismatch, n))

    for field in field_weights:
        if not field in counters:
            continue
        for mismatch, n in (field_mismatch_sums[field].most_common(n)):
            print('')
            print('== Field "%s" mismatch "%s" query details' % (field, mismatch))
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
    field_weights = ['opcode', 'qcase', 'qtype', 'rcode', 'flags', 'answer', 'authority']  #, 'additional', 'edns']
    global_stats, field_stats = process_results(field_weights, diff_stream)
    #pprint(field_stats)
    print_results(global_stats, field_weights, field_stats)

if __name__ == '__main__':
    main()
