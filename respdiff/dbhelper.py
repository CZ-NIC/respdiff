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


def qid2key(qid):
    """Encode query ID to database key"""
    return str(qid).encode('ascii')
