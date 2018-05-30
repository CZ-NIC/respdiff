from abc import ABC
from contextlib import contextmanager
import os
import struct
import sys
import time
from typing import (  # noqa
    Any, Callable, Dict, Iterable, Iterator, List, Mapping, Optional, Tuple, Sequence)

import lmdb

from .dataformat import QID

# upon import, check we're on a little endian platform
assert sys.byteorder == 'little', 'Big endian platforms are not supported'

ResolverID = str
RepliesBlob = bytes
QKey = bytes
WireFormat = bytes


VERSION = '2018-05-21'


def qid2key(qid: QID) -> QKey:
    return struct.pack('<I', qid)


def key2qid(key: QKey) -> QID:
    return struct.unpack('<I', key)[0]


def get_query_iterator(
            lmdb_,
            qids: Iterable[QID]
        ) -> Iterator[Tuple[QID, WireFormat]]:
    qdb = lmdb_.get_db(LMDB.QUERIES)
    with lmdb_.env.begin(qdb) as txn:
        for qid in qids:
            key = qid2key(qid)
            qwire = txn.get(key)
            yield qid, qwire


class LMDB:
    ANSWERS = b'answers'
    DIFFS = b'diffs'
    QUERIES = b'queries'
    META = b'meta'

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
            msg = 'LMDB environment "{}" does not contain DB "{}"! '.format(
                self.path, dbname.decode('utf-8'))
            raise RuntimeError(msg)
        if check_notexists and self.exists_db(dbname):
            msg = ('LMDB environment "{}" already contains DB "{}"! '
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
            raise ValueError("Database {} isn't open!".format(dbname.decode('utf-8')))

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

    def __init__(self, wire: Optional[WireFormat], time_: float = 0) -> None:
        if wire is None:
            self.wire = b''
            self.time = float('+inf')
        else:
            self.wire = wire
            self.time = time_

    @property
    def timeout(self) -> bool:
        return self.time == float('+inf')

    def __eq__(self, other) -> bool:
        if self.timeout and other.timeout:
            return True
        # float equality comparison: use 10^-7 tolerance since it's less than available
        # resoltuion from the time_int integer value (which is 10^-6)
        return self.wire == other.wire and \
            abs(self.time - other.time) < 10 ** -7

    @property
    def time_int(self) -> int:
        if self.time == float('+inf'):
            return self.TIMEOUT_INT
        value = round(self.time * (10 ** 6))
        if value > self.TIMEOUT_INT:
            raise ValueError(
                'Maximum time value exceeded: (value: "{}", max: {})'.format(
                    value, self.TIMEOUT_INT))
        return value

    @property
    def binary(self) -> bytes:
        length = len(self.wire)
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
            time_ = float('+inf')
        else:
            time_ = time_int / (10 ** 6)
        reply = DNSReply(wire, time_)

        return reply, buff[offset:]


class DNSRepliesFactory:
    """Thread-safe factory to parse DNSReply objects from binary blob."""
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
            raise ValueError('Trailing data in buffer')
        return replies

    def serialize(self, replies: Mapping[ResolverID, DNSReply]) -> bytes:
        if len(replies) > len(self.servers):
            raise ValueError('Extra unexpected data to serialize!')
        data = []
        for server in self.servers:
            try:
                reply = replies[server]
            except KeyError:
                raise ValueError('Missing reply for server "{}"!'.format(server))
            else:
                data.append(reply.binary)
        return b''.join(data)


class Database(ABC):
    DB_NAME = b''

    def __init__(self, lmdb_, create: bool = False) -> None:
        self.lmdb = lmdb_
        self.db = None
        self.create = create

    @contextmanager
    def transaction(self, write: bool = False):
        # ensure database is open
        if self.db is None:
            if not self.DB_NAME:
                raise RuntimeError('No database to initialize!')
            try:
                self.db = self.lmdb.get_db(self.DB_NAME)
            except ValueError:
                try:
                    self.db = self.lmdb.open_db(self.DB_NAME, create=self.create)
                except lmdb.Error as exc:
                    raise RuntimeError('Failed to open LMDB database: {}'.format(exc))

        with self.lmdb.env.begin(self.db, write=write) as txn:
            yield txn

    def read_key(self, key: bytes) -> bytes:
        with self.transaction() as txn:
            data = txn.get(key)
        if data is None:
            raise KeyError("Missing '{}' key in '{}' database!".format(
                key.decode('ascii'), self.DB_NAME.decode('ascii')))
        return data

    def write_key(self, key: bytes, value: bytes) -> None:
        with self.transaction(write=True) as txn:
            txn.put(key, value)


class MetaDatabase(Database):
    DB_NAME = LMDB.META
    KEY_VERSION = b'version'
    KEY_START_TIME = b'start_time'
    KEY_END_TIME = b'end_time'
    KEY_SERVERS = b'servers'
    KEY_NAME = b'name'

    def __init__(
                self,
                lmdb_,
                servers: Sequence[ResolverID],
                create: bool = False
            ) -> None:
        super(MetaDatabase, self).__init__(lmdb_, create)
        if create:
            self.write_servers(servers)
        else:
            self.check_version()
            self.check_servers(servers)

    def read_servers(self) -> List[ResolverID]:
        servers = []
        ndata = self.read_key(self.KEY_SERVERS)
        n, = struct.unpack('<I', ndata)
        for i in range(n):
            key = self.KEY_NAME + str(i).encode('ascii')
            server = self.read_key(key)
            servers.append(server.decode('ascii'))
        return servers

    def write_servers(self, servers: Sequence[ResolverID]) -> None:
        if not servers:
            raise ValueError("Empty list of servers!")
        n = struct.pack('<I', len(servers))
        self.write_key(self.KEY_SERVERS, n)
        for i, server in enumerate(servers):
            key = self.KEY_NAME + str(i).encode('ascii')
            self.write_key(key, server.encode('ascii'))

    def check_servers(self, servers: Sequence[ResolverID]) -> None:
        db_servers = self.read_servers()
        if not servers == db_servers:
            raise NotImplementedError(
                'Servers defined in config differ from the ones in "meta" database! '
                '(config: "{}", meta db: "{}")'.format(servers, db_servers))

    def write_version(self) -> None:
        self.write_key(self.KEY_VERSION, VERSION.encode('ascii'))

    def check_version(self) -> None:
        version = self.read_key(self.KEY_VERSION).decode('ascii')
        if version != VERSION:
            raise NotImplementedError(
                'LMDB version mismatch! (expected "{}", got "{}")'.format(
                    VERSION, version))

    def write_start_time(self, timestamp: Optional[int] = None) -> None:
        self._write_timestamp(self.KEY_START_TIME, timestamp)

    def write_end_time(self, timestamp: Optional[int] = None) -> None:
        self._write_timestamp(self.KEY_END_TIME, timestamp)

    def read_start_time(self) -> Optional[int]:
        return self._read_timestamp(self.KEY_START_TIME)

    def read_end_time(self) -> Optional[int]:
        return self._read_timestamp(self.KEY_END_TIME)

    def _read_timestamp(self, key: bytes) -> Optional[int]:
        try:
            data = self.read_key(key)
        except KeyError:
            return None
        else:
            return struct.unpack('<I', data)[0]

    def _write_timestamp(self, key: bytes, timestamp: Optional[int]) -> None:
        if timestamp is None:
            timestamp = round(time.time())
        data = struct.pack('<I', timestamp)
        self.write_key(key, data)
