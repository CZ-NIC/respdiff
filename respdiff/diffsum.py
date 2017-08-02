#!/usr/bin/env python3

import argparse
import collections
import logging
import pickle
import sys

import dns.rdatatype
import lmdb

import cfg
import dbhelper
from msgdiff import DataMismatch  # needed for unpickling

def process_diff(field_weights, field_stats, qwire, diff):
    found = False
    for field in field_weights:
        if field in diff:
            significant_field = field
            break
    assert significant_field  # field must be in field_weights
    if significant_field == 'answer':
        return

    qmsg = dns.message.from_wire(qwire)
    question = (qmsg.question[0].name, qmsg.question[0].rdtype)

    field_mismatches = field_stats.setdefault(field, {})
    mismatch = diff[significant_field]
    mismatch_key = (mismatch.exp_val, mismatch.got_val)
    mismatch_counter = field_mismatches.setdefault(mismatch_key, collections.Counter())
    mismatch_counter[question] += 1


# FIXME: this code is ugly, refactor it
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
    for qid, qwire, others_agree, target_diff in diff_generator:
        #print(qid, others_agree, target_diff)
        if not others_agree:
            global_stats['others_disagree'] += 1
            continue

        if not target_diff:  # everybody agreed, nothing to count
            continue

        #print('(%s, %s): ' % (qid, question))
        #print(target_diff, ',')

        global_stats['target_disagrees'] += 1
        process_diff(field_weights, field_stats, qwire, target_diff)

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

    if not field_sums.keys():
        return
    print('')
    # print('== Field statistics: field - count - % of mismatches')
    maxnamelen = maxlen(field_sums.keys())
    maxcntlen = maxlen(field_sums.values())
    print('== {:{}}    {:{}}    {}'.format(
        'Field', maxnamelen - (len('count') - maxcntlen),
        'count', maxcntlen,
        '% of mismatches'))

    for field, n in (field_sums.most_common()):
        print('{:{}}    {:{}}     {:3.0f} %'.format(
            field, maxnamelen + 3,
            n, maxcntlen + 3,
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
            'Got', (maxvallen - (len('count') - maxcntlen)) if maxvallen - (len('count') - maxcntlen) > 1 else 1,
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
        for mismatch, n in (field_mismatch_sums[field].most_common()):
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
    try:
        qdb = lenv.open_db(key=dbhelper.QUERIES_DB_NAME, create=False, **dbhelper.db_open)
        adb = lenv.open_db(key=dbhelper.ANSWERS_DB_NAME, create=False, **dbhelper.db_open)
        ddb = lenv.open_db(key=dbhelper.DIFFS_DB_NAME, create=False, **dbhelper.db_open)
    except lmdb.NotFoundError:
        logging.critical('Unable to generate statistics. LMDB does not contain queries, answers, or diffs!')
        raise
    return lenv, qdb, adb, ddb

def read_diffs_lmdb(levn, qdb, ddb):
    with levn.begin() as txn:
        with txn.cursor(ddb) as diffcur:
            for qid, diffblob in diffcur:
                others_agree, diff = pickle.loads(diffblob)
                qwire = txn.get(qid, db=qdb)
                yield (qid, qwire, others_agree, diff)

def main():
    logging.basicConfig(format='%(levelname)s %(message)s', level=logging.DEBUG)
    parser = argparse.ArgumentParser(
        description='read queries from LMDB, send them in parallel to servers '
                    'listed in configuration file, and record answers into LMDB')
    parser.add_argument('-c', '--config', default='respdiff.cfg', dest='cfgpath',
                        help='config file (default: respdiff.cfg)')
    parser.add_argument('envdir', type=str,
                        help='LMDB environment to read queries and answers from')
    args = parser.parse_args()
    config = cfg.read_cfg(args.cfgpath)
    field_weights = config['report']['field_weights']

    lenv, qdb, adb, ddb = open_db(args.envdir)
    diff_stream = read_diffs_lmdb(lenv, qdb, ddb)
    global_stats, field_stats = process_results(field_weights, diff_stream)
    with lenv.begin() as txn:
        global_stats['queries'] = txn.stat(qdb)['entries']
        global_stats['answers'] = txn.stat(adb)['entries']
    print_results(global_stats, field_weights, field_stats)

if __name__ == '__main__':
    main()
