import lmdb


ANSWERS_DB_NAME = b'answers'
DIFFS_DB_NAME = b'diffs'
QUERIES_DB_NAME = b'queries'


env_open = {
    'map_size': 1024**4,
    'max_readers': 64,
    'max_dbs': 5,
    'max_spare_txns': 64,
}

db_open = {
    'reverse_key': True
}


def key_stream(lenv, db):
    """
    yield all keys from given db
    """
    with lenv.begin(db) as txn:
        with txn.cursor(db) as cur:
            cont = cur.first()
            while cont:
                yield cur.key()
                cont = cur.next()


def key_value_stream(lenv, db):
    """
    yield all (key, value) pairs from given db
    """
    with lenv.begin(db) as txn:
        cur = txn.cursor(db)
        for key, blob in cur:
            yield (key, blob)


def qid2key(qid):
    """Encode query ID to database key"""
    return str(qid).encode('ascii')


def db_exists(envdir, dbname):
    """
    Determine if named DB exists in environment specified by path.
    """
    config = env_open.copy()
    config['path'] = envdir
    config['readonly'] = True
    try:
        with lmdb.Environment(**config) as env:
            db = env.open_db(key=dbname, **db_open, create=False)
            return True
    except (lmdb.NotFoundError, lmdb.Error):
        return False
