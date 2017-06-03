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
    field_stats = {}

    stats = {
        'queries': 0,
        'others_disagree': 0,
        'target_disagrees': 0,
        'diff_field_count': collections.Counter()
        }
    uniq = {}
    queries = collections.Counter()

    #print('diffs = {')
    for qid, question, others_agree, target_diff in diff_generator:
        stats['queries'] += 1  # FIXME
        #print(qid, others_agree, target_diff)
        if not others_agree:
            stats['others_disagree'] += 1
            continue

        if not target_diff:  # everybody agreed, nothing to count
            continue

        #print('(%s, %s): ' % (qid, question))
        #print(target_diff, ',')

        stats['target_disagrees'] += 1
        process_diff(field_weights, field_stats, question, target_diff)

    #print('}')
    return field_stats

def print_results(weights, counters, n=10):
    # global stats
    field_totals = {field: sum(counter.values()) for field, counter in counters.items()}
    pprint(field_totals)

    for field in weights:
        if field in counters:
            counter = counters[field]
            print('mismatches in field %s: %s mismatches' % (field, sum(counter.values())))
            print_field_queries(field, counter, n)
            print('')
    return
        #if field == 'answer':
        #    continue
        #queries.update([question])
        ##print(type(question))
        ##print(question)
        #uniq.setdefault(field, collections.Counter()).update([value])

    stats['diff_field_count'] = dict(stats['diff_field_count'])
    print('stats = ')
    pprint(stats)
    print('uniq = ')
    #for field in uniq:
    #    uniq[field] = collections.OrderedDict(uniq[field].most_common(100))
    pprint(uniq)

def print_field_queries(field, counter, n):
    #print('queries leading to mismatch in field "%s":' % field)
    for query, count in counter.most_common(n):
        qname, qtype = query
        qtype = dns.rdatatype.to_text(qtype)
        print("%s %s: %s mismatches" % (qname, qtype, count))

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
    field_stats = process_results(field_weights, diff_stream)
    pprint(field_stats)
    #print_results(field_weights, field_counters)

if __name__ == '__main__':
    main()
