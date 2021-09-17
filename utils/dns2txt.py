#!/usr/bin/python3

import sys

import dns.message

with open(sys.argv[1], 'rb') as f:
    m = dns.message.from_wire(f.read())
print(str(m))
