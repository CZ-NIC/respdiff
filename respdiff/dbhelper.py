import logging
import os
import struct
import sys
from typing import Any, Dict, Iterator, Optional, Tuple, Sequence  # noqa

import lmdb

from dataformat import QID


ResolverID = str
RepliesBlob = bytes
QKey = bytes
WireFormat = bytes


def qid2key(qid: QID) -> QKey:
    return struct.pack('<I', qid)


def key2qid(key: QKey) -> QID:
    return struct.unpack('<I', key)[0]


class LMDB:
    ANSWERS = b'answers'
    DIFFS = b'diffs'
    QUERIES = b'queries'

    ENV_DEFAULTS = {
        'map_size': 10 * 1024**3,  # 10 G
        'max_readers': 128,
        'max_dbs': 5,
        'max_spare_txns': 64,
    }  # type: Dict[str, Any]

    DB_OPEN_DEFAULTS = {
        'integerkey': False,
        # surprisingly, optimal configuration seems to be
        # native integer as database key *without*
        # integerkey support in LMDB
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

    def open_db(self, dbname: bytes, create: bool = False,
                check_notexists: bool = False, drop: bool = False):
        assert self.env is not None, "LMDB wasn't initialized!"
        if not create and not self.exists_db(dbname):
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

    def key_stream(self, dbname: bytes) -> Iterator[bytes]:
        """yield all keys from given db"""
        db = self.get_db(dbname)
        with self.env.begin(db) as txn:
            cur = txn.cursor(db)
            for key in cur.iternext(keys=True, values=False):
                yield key

    def key_value_stream(self, dbname: bytes) -> Iterator[Tuple[bytes, bytes]]:
        """yield all (key, value) pairs from given db"""
        db = self.get_db(dbname)
        with self.env.begin(db) as txn:
            cur = txn.cursor(db)
            for key, blob in cur:
                yield key, blob


class DNSReply:
    TIMEOUT_INT = 4294967295
    SIZEOF_INT = 4
    SIZEOF_SHORT = 2

    def __init__(self, wire: Optional[WireFormat], time: float = 0) -> None:
        if wire is None:
            self.wire = b''
            self.time = float('+inf')
        else:
            self.wire = wire
            self.time = time

    @property
    def timeout(self) -> bool:
        return self.time == float('+inf')

    def __eq__(self, other) -> bool:
        if self.timeout and other.timeout:
            return True
        return self.wire == other.wire and \
            abs(self.time - other.time) < 10 ** -7

    @property
    def time_int(self) -> int:
        if self.time == float('+inf'):
            return self.TIMEOUT_INT
        value = round(self.time * (10 ** 6))
        if value > self.TIMEOUT_INT:
            raise ValueError('Maximum time value exceeded')
        return value

    @property
    def binary(self) -> bytes:
        length = len(self.wire)
        assert length < 2**(self.SIZEOF_SHORT*8), 'Maximum wire format length exceeded'
        return struct.pack('<I', self.time_int) + struct.pack('<H', length) + self.wire

    @classmethod
    def from_binary(cls, buff: bytes) -> Tuple['DNSReply', bytes]:
        if len(buff) < (cls.SIZEOF_INT + cls.SIZEOF_SHORT):
            raise ValueError('Missing data in binary format')
        offset = 0
        time_int, = struct.unpack_from('<I', buff, offset)
        offset += cls.SIZEOF_INT
        length, = struct.unpack_from('<H', buff, offset)
        offset += cls.SIZEOF_SHORT
        wire = buff[offset:(offset+length)]
        offset += length

        if len(wire) != length:
            raise ValueError('Missing data in binary format')

        if time_int == cls.TIMEOUT_INT:
            time = float('+inf')
        else:
            time = time_int / (10 ** 6)
        reply = DNSReply(wire, time)

        return reply, buff[offset:]


class DNSRepliesFactory:
    def __init__(self, servers: Sequence[ResolverID]) -> None:
        if not servers:
            raise ValueError('One or more servers have to be specified')
        self.servers = servers

    def parse(self, buff: bytes) -> Dict[ResolverID, DNSReply]:
        replies = {}
        for server in self.servers:
            reply, buff = DNSReply.from_binary(buff)
            replies[server] = reply
        if buff:
            logging.warning('Trailing data in buffer')
        return replies


# upon import, check we're on a little endian platform
assert sys.byteorder == 'little', 'Big endian platforms are not supported'
