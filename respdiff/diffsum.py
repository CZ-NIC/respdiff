#!/usr/bin/env python3

import argparse
import collections
import logging
import pickle

import dns.rdatatype

import cfg
from dbhelper import LMDB
from msgdiff import DataMismatch  # NOQA: needed for unpickling


def process_diff(field_weights, field_stats, qwire, diff):
    for field in field_weights:
        if field in diff:
            significant_field = field
            break
    assert significant_field  # field must be in field_weights
    if significant_field == 'answer':
        return

    qmsg = dns.message.from_wire(qwire)
    question = (qmsg.question[0].name, qmsg.question[0].rdtype)

    field_mismatches = field_stats.setdefault(field, {})  # pylint: disable=undefined-loop-variable
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

    for _, qwire, others_agree, target_diff in diff_generator:
        if not others_agree:
            global_stats['others_disagree'] += 1
            continue

        if not target_diff:  # everybody agreed, nothing to count
            continue

        global_stats['target_disagrees'] += 1
        process_diff(field_weights, field_stats, qwire, target_diff)

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
    return mismatch


def maxlen(iterable):
    return max(len(str(it)) for it in iterable)


def print_results(gstats, field_weights, counters, n=10):
    # global stats
    field_sums, field_mismatch_sums = combine_stats(counters)

    maxcntlen = maxlen(gstats.values())
    others_agree = gstats['answers'] - gstats['others_disagree']
    target_disagrees = gstats['target_disagrees']

    global_report = '\n'.join([
        '== Global statistics',
        'duration           {duration:{ml}} s',
        'queries            {queries:{ml}}',
        'answers            {answers:{ml}}    {answers_pct:6.2f} % of queries',
        ('others agree       {oth_agr:{ml}}    {oth_agr_pct:6.2f} % of answers'
         '(ignoring {oth_agr_ignore_pct:.2f} % of answers)'),
        ('target disagrees   {tgt_disagr:{ml}}    {tgt_disagr_pct:6.2f} % of '
         'matching answers from others')
    ])

    print(global_report.format(
        ml=maxcntlen,
        duration=gstats['duration'],
        queries=gstats['queries'],
        answers=gstats['answers'],
        answers_pct=100.0 * gstats['answers'] / gstats['queries'],
        oth_agr=others_agree,
        oth_agr_pct=100.0 * others_agree / gstats['answers'],
        oth_agr_ignore_pct=100.0 * gstats['others_disagree'] / gstats['answers'],
        tgt_disagr=gstats['target_disagrees'],
        tgt_disagr_pct=100.0 * gstats['target_disagrees'] / others_agree))

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

    for field, count in field_sums.most_common():
        print('{:{}}    {:{}}     {:3.0f} %'.format(
            field, maxnamelen + 3,
            count, maxcntlen + 3, 100.0 * count / target_disagrees))

    for field in field_weights:
        if field not in field_mismatch_sums:
            continue
        print('')
        print('== Field "%s" mismatch statistics' % field)
        maxvallen = max((max(len(str(mismatch2str(mism)[0])), len(str(mismatch2str(mism)[1])))
                         for mism in field_mismatch_sums[field].keys()))
        maxcntlen = maxlen(field_mismatch_sums[field].values())
        print('{:{}}  !=  {:{}}    {:{}}    {}'.format(
            'Expected', maxvallen,
            'Got',
            (maxvallen - (len('count') - maxcntlen)) if maxvallen - (len('count') - maxcntlen) > 1
            else 1,
            'count', maxcntlen,
            '% of mismatches'
        ))
        for mismatch, count in field_mismatch_sums[field].most_common():
            mismatch = mismatch2str(mismatch)
            print('{:{}}  !=  {:{}}    {:{}}    {:3.0f} %'.format(
                str(mismatch[0]), maxvallen,
                str(mismatch[1]), maxvallen,
                count, maxcntlen,
                100.0 * count / target_disagrees))

    for field in field_weights:
        if field not in counters:
            continue
        for mismatch, count in field_mismatch_sums[field].most_common():
            display_limit = count if n == 0 else n
            limit_msg = ''
            if display_limit < count:
                limit_msg = ' (displaying {} out of {} results)'.format(display_limit, count)
            print('')
            print('== Field "%s" mismatch %s query details%s' % (field, mismatch, limit_msg))
            counter = counters[field][mismatch]
            print_field_queries(counter, display_limit)


def print_field_queries(counter, n):
    for query, count in counter.most_common(n):
        qname, qtype = query
        qtype = dns.rdatatype.to_text(qtype)
        print("%s %s\t\t%s mismatches" % (qname, qtype, count))


def read_diffs_lmdb(lmdb):
    qdb = lmdb.get_db(LMDB.QUERIES)
    ddb = lmdb.get_db(LMDB.DIFFS)
    with lmdb.env.begin() as txn:
        with txn.cursor(ddb) as diffcur:
            for qid, diffblob in diffcur:
                others_agree, diff = pickle.loads(diffblob)
                qwire = txn.get(qid, db=qdb)
                yield qid, qwire, others_agree, diff


def main():
    logging.basicConfig(format='%(levelname)s %(message)s', level=logging.DEBUG)
    parser = argparse.ArgumentParser(
        description='read queries from LMDB, send them in parallel to servers '
                    'listed in configuration file, and record answers into LMDB')
    parser.add_argument('-c', '--config', default='respdiff.cfg', dest='cfgpath',
                        help='config file (default: respdiff.cfg)')
    parser.add_argument('-l', '--limit', type=int, default=10,
                        help='number of displayed mismatches in fields (default: 10; '
                             'use 0 to display all)')
    parser.add_argument('envdir', type=str,
                        help='LMDB environment to read queries and answers from')
    args = parser.parse_args()
    config = cfg.read_cfg(args.cfgpath)
    field_weights = config['report']['field_weights']

    with LMDB(args.envdir, readonly=True) as lmdb:
        qdb = lmdb.open_db(LMDB.QUERIES)
        adb = lmdb.open_db(LMDB.ANSWERS)
        lmdb.open_db(LMDB.DIFFS)
        sdb = lmdb.open_db(LMDB.STATS)
        diff_stream = read_diffs_lmdb(lmdb)
        global_stats, field_stats = process_results(field_weights, diff_stream)
        with lmdb.env.begin() as txn:
            global_stats['queries'] = txn.stat(qdb)['entries']
            global_stats['answers'] = txn.stat(adb)['entries']
        with lmdb.env.begin(sdb) as txn:
            stats = pickle.loads(txn.get(b'global_stats'))
    global_stats['duration'] = round(stats['end_time'] - stats['start_time'])
    print_results(global_stats, field_weights, field_stats, n=args.limit)


if __name__ == '__main__':
    main()
