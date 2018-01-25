import pickle
import os
import sys

from dbhelper import LMDB


def read_blobs_lmdb(lmdb, db, qid):
    with lmdb.env.begin(db) as txn:
        blob = txn.get(qid)
        assert blob
        answers = pickle.loads(blob)
        return answers


def write_blobs(blob_dict, workdir):
    for k, v in blob_dict.items():
        filename = os.path.join(workdir, k)
        with open(filename, 'wb') as outfile:
            outfile.write(v)


def main():
    with LMDB(sys.argv[1], readonly=True) as lmdb:
        db = lmdb.open_db(LMDB.ANSWERS)
        qid = str(int(sys.argv[2])).encode('ascii')
        blobs = read_blobs_lmdb(lmdb, db, qid)
        write_blobs(blobs, sys.argv[3])


if __name__ == '__main__':
    main()
