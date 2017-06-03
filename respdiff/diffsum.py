import collections
import pickle
from pprint import pprint
import sys

import dns.rdatatype
import lmdb

import dbhelper

def process_results(diff_generator):
    stats = {
        'queries': 0,
        'others_disagree': 0,
        'target_disagrees': 0,
        'diff_field_count': collections.Counter()
        }
    uniq = {}
    queries = collections.Counter()

    print('diffs = {')
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

def main():
    lenv, qdb, adb, ddb = open_db(sys.argv[1])

if __name__ == '__main__':
    main()
