import pickle
from pprint import pprint
import os
import sys

import lmdb

import dbhelper
import msgdiff


def read_blobs_lmdb(lenv, db, qid):
    with lenv.begin(db) as txn:
        blob = txn.get(qid)
        assert blob
        answers = pickle.loads(blob)
        return answers


def write_blobs(blob_dict, workdir):
    for k, v in blob_dict.items():
        filename = os.path.join(workdir, k)
        with open(filename, 'wb') as outfile:
            outfile.write(v)


config = dbhelper.env_open.copy()
config.update({
    'path': sys.argv[1],
    'readonly': True
})
lenv = lmdb.Environment(**config)
db = lenv.open_db(key=b'answers', **dbhelper.db_open, create=False)

qid = str(int(sys.argv[2])).encode('ascii')
blobs = read_blobs_lmdb(lenv, db, qid)
write_blobs(blobs, sys.argv[3])
lenv.close()
