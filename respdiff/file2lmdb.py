import pickle
from pprint import pprint
import os
import sys

import lmdb

import lmdbcfg
import msgdiff


def write_lmdb(qid, wire, lenv, db):
    key = str(qid).encode('ascii')
    with lenv.begin(db, write=True) as txn:
        txn.put(key, wire)


def read_blobs(workdir):
    answers = {}
    for filename in os.listdir(workdir):
        if filename == 'q.dns':
            continue
        if not filename.endswith('.dns'):
            continue
        name = filename[:-4]
        filename = os.path.join(workdir, filename)
        with open(filename, 'rb') as msgfile:
            answers[name] = msgfile.read()
    return answers


config = lmdbcfg.env_open.copy()
config.update({
    'path': sys.argv[2],
    'sync': False,    # unsafe but fast
    'writemap': True  # we do not care, this is a new database
    })
lenv = lmdb.Environment(**config)
db = lenv.open_db(key=b'answers', **lmdbcfg.db_open)

for dirname in msgdiff.find_querydirs(sys.argv[1]):
    print(dirname)
    answers = read_blobs(dirname)
    qid = int(dirname.split('/')[-1])
    blob = pickle.dumps(answers)
    write_lmdb(qid, blob, lenv, db)

pprint(lenv.stat())
