import argparse
import sys

import dns.name
import dns.message
import dns.rdataclass
import dns.rdatatype


qparser = argparse.ArgumentParser(description='Generate DNS message with query')
qparser.add_argument('qname', type=lambda x: int_or_fromtext(x, dns.name.from_text))
qparser.add_argument('qclass', type=lambda x: int_or_fromtext(x, dns.rdataclass.from_text), nargs='?', default='IN')
qparser.add_argument('qtype', type=lambda x: int_or_fromtext(x, dns.rdatatype.from_text))

def int_or_fromtext(value, fromtext):
    try:
        return int(value)
    except ValueError:
        return fromtext(value)

def qfromtext(*args):
    arglist = ['--'] + args[0]
    args = qparser.parse_args(arglist)
    return dns.message.make_query(args.qname, args.qtype, args.qclass, want_dnssec=True)

def qsfrompcap(pcapname):
    pass


def is_blacklisted(msg):
    if len(msg.question) >= 1:
        if msg.question[0].rdtype == dns.rdatatype.ANY:
            return True
    return False

def main():
    qry = qfromtext(sys.argv[1:])
    if is_blacklisted(qry):
        sys.exit('query blacklisted')
    sys.stdout.write(qry.to_wire())


if __name__ == "__main__":
    main()
