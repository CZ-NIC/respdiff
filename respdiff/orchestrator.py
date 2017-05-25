import multiprocessing.pool as pool
import os

import sendrecv

timeout = 5
resolvers = [
        ('kresd', '127.0.0.1', 5353),
        ('unbound', '127.0.0.1', 53535),
        ('bind', '127.0.0.1', 53533)
    ]

# find query files

def find_querydirs(workdir):
    for root, dirs, files in os.walk('.'):
        dirs.sort()
        if not 'q.dns' in files:
            continue
        #print('yield %s' % root)
        yield root

#selector.close()  # TODO

with pool.Pool(
        processes=8,
        initializer=sendrecv.worker_init,
        initargs=[resolvers, timeout]) as p:
    p.map(sendrecv.query_resolvers, find_querydirs('.'))
