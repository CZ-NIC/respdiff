from typing import Iterable, Iterator, Tuple

from .dataformat import QID
from .dbhelper import LMDB, qid2key, WireFormat


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
