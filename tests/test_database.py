import os
import pytest

from respdiff.database import (
    DNSReply,
    DNSRepliesFactory,
    LMDB,
    MetaDatabase,
    BIN_FORMAT_VERSION,
    qid2key,
)


LMDB_DIR = os.path.join(
    os.path.abspath(os.path.dirname(__file__)), "lmdb", BIN_FORMAT_VERSION
)


def create_reply(wire, time):
    if time is not None:
        return DNSReply(wire, time)
    return DNSReply(wire)


def test_dns_reply_timeout():
    reply = DNSReply(None)
    assert reply.timeout
    assert reply.time == float("+inf")


@pytest.mark.parametrize(
    "wire1, time1, wire2, time2, equals",
    [
        (None, None, None, None, True),
        (None, None, None, 1, True),
        (b"", None, b"", None, True),
        (b"", None, b"", 1, False),
        (b"a", None, b"a", None, True),
        (b"a", None, b"b", None, False),
        (b"a", None, b"aa", None, False),
    ],
)
def test_dns_reply_equals(wire1, time1, wire2, time2, equals):
    r1 = create_reply(wire1, time1)
    r2 = create_reply(wire2, time2)
    assert (r1 == r2) == equals


@pytest.mark.parametrize(
    "time, time_int",
    [
        (None, 0),
        (0, 0),
        (1.43, 1430000),
        (0.4591856, 459186),
    ],
)
def test_dns_reply_time_int(time, time_int):
    reply = create_reply(b"", time)
    assert reply.time_int == time_int


DR_TIMEOUT = DNSReply(None)
DR_TIMEOUT_BIN = b"\xff\xff\xff\xff\x00\x00"
DR_EMPTY_0 = DNSReply(b"")
DR_EMPTY_0_BIN = b"\x00\x00\x00\x00\x00\x00"
DR_EMPTY_1 = DNSReply(b"", 1)
DR_EMPTY_1_BIN = b"\x40\x42\x0f\x00\x00\x00"
DR_A_0 = DNSReply(b"a")
DR_A_0_BIN = b"\x00\x00\x00\x00\x01\x00a"
DR_A_1 = DNSReply(b"a", 1)
DR_A_1_BIN = b"\x40\x42\x0f\x00\x01\x00a"
DR_ABCD_1 = DNSReply(b"abcd", 1)
DR_ABCD_1_BIN = b"\x40\x42\x0f\x00\x04\x00abcd"


@pytest.mark.parametrize(
    "reply, binary",
    [
        (DR_TIMEOUT, DR_TIMEOUT_BIN),
        (DR_EMPTY_0, DR_EMPTY_0_BIN),
        (DR_EMPTY_1, DR_EMPTY_1_BIN),
        (DR_A_0, DR_A_0_BIN),
        (DR_A_1, DR_A_1_BIN),
        (DR_ABCD_1, DR_ABCD_1_BIN),
    ],
)
def test_dns_reply_serialization(reply, binary):
    assert reply.binary == binary


@pytest.mark.parametrize(
    "binary, reply, remaining",
    [
        (DR_TIMEOUT_BIN, DR_TIMEOUT, b""),
        (DR_EMPTY_0_BIN, DR_EMPTY_0, b""),
        (DR_EMPTY_1_BIN, DR_EMPTY_1, b""),
        (DR_A_0_BIN, DR_A_0, b""),
        (DR_A_1_BIN, DR_A_1, b""),
        (DR_ABCD_1_BIN, DR_ABCD_1, b""),
        (DR_A_1_BIN + b"a", DR_A_1, b"a"),
        (DR_ABCD_1_BIN + b"bcd", DR_ABCD_1, b"bcd"),
    ],
)
def test_dns_reply_deserialization(binary, reply, remaining):
    got_reply, buff = DNSReply.from_binary(binary)
    assert reply == got_reply
    assert buff == remaining


def test_dns_replies_factory():
    with pytest.raises(ValueError):
        DNSRepliesFactory([])

    rf = DNSRepliesFactory(["a"])
    replies = rf.parse(DR_TIMEOUT_BIN)
    assert replies["a"] == DR_TIMEOUT

    rf2 = DNSRepliesFactory(["a", "b"])
    bin_data = DR_A_0_BIN + DR_ABCD_1_BIN
    replies = rf2.parse(bin_data)
    assert replies["a"] == DR_A_0
    assert replies["b"] == DR_ABCD_1

    with pytest.raises(ValueError):
        rf2.parse(DR_A_0_BIN + b"a")

    assert rf2.serialize(replies) == bin_data


INT_3M = 3000000000
TIME_3M = 3000.0


def test_lmdb_answers_single_server():
    envdir = os.path.join(LMDB_DIR, "answers_single_server")
    with LMDB(envdir) as lmdb:
        adb = lmdb.open_db(LMDB.ANSWERS)
        meta = MetaDatabase(lmdb, ["kresd"])
        assert meta.read_start_time() == INT_3M
        assert meta.read_end_time() == INT_3M

        servers = meta.read_servers()
        assert len(servers) == 1
        assert servers[0] == "kresd"

        with lmdb.env.begin(adb) as txn:
            data = txn.get(qid2key(INT_3M))
        df = DNSRepliesFactory(servers)
        replies = df.parse(data)
        assert len(replies) == 1
        assert replies[servers[0]] == DNSReply(b"a", TIME_3M)


def test_lmdb_answers_multiple_servers():
    envdir = os.path.join(LMDB_DIR, "answers_multiple_servers")
    with LMDB(envdir) as lmdb:
        adb = lmdb.open_db(LMDB.ANSWERS)
        meta = MetaDatabase(lmdb, ["kresd", "bind", "unbound"])
        assert meta.read_start_time() is None
        assert meta.read_end_time() is None

        servers = meta.read_servers()
        assert len(servers) == 3
        assert servers[0] == "kresd"
        assert servers[1] == "bind"
        assert servers[2] == "unbound"

        df = DNSRepliesFactory(servers)

        with lmdb.env.begin(adb) as txn:
            data = txn.get(qid2key(INT_3M))

        replies = df.parse(data)
        assert len(replies) == 3
        assert replies[servers[0]] == DNSReply(b"", TIME_3M)
        assert replies[servers[1]] == DNSReply(b"ab", TIME_3M)
        assert replies[servers[2]] == DNSReply(b"a", TIME_3M)
