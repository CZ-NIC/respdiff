#!/usr/bin/env python3
"""
Create testing LMDB data
"""

import os
import struct

import lmdb


VERSION = "2018-05-21"
CREATE_ENVS = {
    "2018-05-21": [
        "answers_single_server",
        "answers_multiple_servers",
    ],
}


BIN_INT_3000000000 = b"\x00^\xd0\xb2"


class LMDBExistsError(Exception):
    pass


def open_env(version, name):
    path = os.path.join(version, name)
    if os.path.exists(os.path.join(path, "data.mdb")):
        raise LMDBExistsError
    if not os.path.exists(path):
        os.makedirs(path)
    return lmdb.Environment(path=path, max_dbs=5, create=True)


def create_answers_single_server():
    env = open_env(VERSION, "answers_single_server")
    mdb = env.open_db(key=b"meta", create=True)
    with env.begin(mdb, write=True) as txn:
        txn.put(b"version", VERSION.encode("ascii"))
        txn.put(b"start_time", BIN_INT_3000000000)
        txn.put(b"end_time", BIN_INT_3000000000)
        txn.put(b"servers", struct.pack("<I", 1))
        txn.put(b"name0", "kresd".encode("ascii"))

    adb = env.open_db(key=b"answers", create=True)
    with env.begin(adb, write=True) as txn:
        answer = BIN_INT_3000000000
        answer += struct.pack("<H", 1)
        answer += b"a"
        txn.put(BIN_INT_3000000000, answer)


def create_answers_multiple_servers():
    env = open_env(VERSION, "answers_multiple_servers")
    mdb = env.open_db(key=b"meta", create=True)
    with env.begin(mdb, write=True) as txn:
        txn.put(b"version", VERSION.encode("ascii"))
        txn.put(b"servers", struct.pack("<I", 3))
        txn.put(b"name0", "kresd".encode("ascii"))
        txn.put(b"name1", "bind".encode("ascii"))
        txn.put(b"name2", "unbound".encode("ascii"))

    adb = env.open_db(key=b"answers", create=True)
    with env.begin(adb, write=True) as txn:
        # kresd
        answer = BIN_INT_3000000000
        answer += struct.pack("<H", 0)
        # bind
        answer += BIN_INT_3000000000
        answer += struct.pack("<H", 2)
        answer += b"ab"
        # unbound
        answer += BIN_INT_3000000000
        answer += struct.pack("<H", 1)
        answer += b"a"
        txn.put(BIN_INT_3000000000, answer)


def main():
    for env_name in CREATE_ENVS[VERSION]:
        try:
            globals()["create_{}".format(env_name)]()
        except LMDBExistsError:
            print("{} exists, skipping".format(env_name))
            continue


if __name__ == "__main__":
    main()
