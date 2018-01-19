from typing import Dict, Any, Tuple, Generator  # NOQA: needed for type hint in comment
import os

import lmdb


def qid2key(qid):
    """Encode query ID to database key"""
    return str(qid).encode('ascii')


class LMDB:
    ANSWERS = b'answers'
    DIFFS = b'diffs'
    QUERIES = b'queries'
    REPROSTATS = b'reprostats'
    STATS = b'stats'

    ENV_DEFAULTS = {
        'map_size': 1024**4,
        'max_readers': 64,
        'max_dbs': 5,
        'max_spare_txns': 64,
    }  # type: Dict[str, Any]

    DB_OPEN_DEFAULTS = {
        'reverse_key': True
    }  # type: Dict[str, Any]

    def __init__(self, path: str, create: bool = False,
                 readonly: bool = False, fast: bool = False) -> None:
        self.path = path
        self.dbs = {}  # type: Dict[bytes, Any]
        self.config = LMDB.ENV_DEFAULTS.copy()
        self.config.update({
            'path': path,
            'create': create,
            'readonly': readonly
        })
        if fast:  # unsafe on crashes, but faster
            self.config.update({
                'writemap': True,
                'sync': False,
                'map_async': True,
            })

        if not os.path.exists(self.path):
            os.makedirs(self.path)
        self.env = lmdb.Environment(**self.config)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.env.close()

    def open_db(self, dbname: bytes, create: bool = False, check_exists: bool = False,
                check_notexists: bool = False, drop: bool = False):
        assert self.env is not None, "LMDB wasn't initialized!"
        if check_exists and not self.exists_db(dbname):
            msg = 'LMDB environment "{}" does not contain DB {}! '.format(
                self.path, dbname.decode('utf-8'))
            raise RuntimeError(msg)
        if check_notexists and self.exists_db(dbname):
            msg = ('LMDB environment "{}" already contains DB {}! '
                   'Overwritting it would invalidate data in the environment, '
                   'terminating.').format(self.path, dbname.decode('utf-8'))
            raise RuntimeError(msg)
        if drop:
            try:
                db = self.env.open_db(key=dbname, create=False, **LMDB.DB_OPEN_DEFAULTS)
                with self.env.begin(write=True) as txn:
                    txn.drop(db)
            except lmdb.NotFoundError:
                pass

        db = self.env.open_db(key=dbname, create=create, **LMDB.DB_OPEN_DEFAULTS)
        self.dbs[dbname] = db
        return db

    def exists_db(self, dbname: bytes) -> bool:
        config = LMDB.ENV_DEFAULTS.copy()
        config.update({
            'path': self.path,
            'readonly': True,
            'create': False
        })
        try:
            with lmdb.Environment(**config) as env:
                env.open_db(key=dbname, **LMDB.DB_OPEN_DEFAULTS, create=False)
                return True
        except (lmdb.NotFoundError, lmdb.Error):
            return False

    def get_db(self, dbname: bytes):
        try:
            return self.dbs[dbname]
        except KeyError:
            raise RuntimeError("Database {} isn't open!".format(dbname.decode('utf-8')))

    def key_stream(self, dbname: bytes):
        """yield all keys from given db"""
        db = self.get_db(dbname)
        with self.env.begin(db) as txn:
            cur = txn.cursor(db)
            for key in cur.iternext(keys=True, values=False):
                yield key

    def key_value_stream(self, dbname: bytes):
        """yield all (key, value) pairs from given db"""
        db = self.get_db(dbname)
        with self.env.begin(db) as txn:
            cur = txn.cursor(db)
            for key, blob in cur:
                yield key, blob
