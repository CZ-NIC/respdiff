#!/usr/bin/python3

import sys

import dns.message

m = dns.message.from_wire(open(sys.argv[1], 'rb').read())
print(str(m))
