import itertools
import multiprocessing.pool as pool
import errno
import os
import sys

import makeq


def read_text():
    i = 0
    for line in sys.stdin:
        line = line.strip()
        if line:
            i += 1
            yield (i, line)
            if i % 10000 == 0:
                print(i)
            #if i > 770000:
            #    print(line)

def gen_qfile(args):
    i, qtext = args
    dirname = '%09d' % i
    qfilename = '%s/q.dns' % dirname
    try:
        os.mkdir(dirname)
    except OSError as ex:
        if not ex.errno == errno.EEXIST:
            raise
    try:
        qry = makeq.qfromtext(qtext.split())
    except BaseException:
        print('line malformed: %s' % qtext)
        return
    if makeq.is_blacklisted(qry):
        return
    with open(qfilename, 'wb') as qfile:
        qfile.write(qry.to_wire())

def main():
    #qstream = itertools.islice(read_text(), 100000)
    qstream = read_text()
    #for i in map(gen_qfile, qstream):
    #    pass
    with pool.Pool() as p:
        for i in p.imap_unordered(gen_qfile, qstream, chunksize=1000):
            pass

if __name__ == '__main__':
    main()

