#!/usr/bin/env python3

import argparse
import base64
import collections
import logging
import sys

import dns.name
import dns.rdatatype
import dns.message

from respdiff import cli, sendrecv
from respdiff.database import DNSRepliesFactory, DNSReply
from respdiff.match import diff_pair

OneResult = collections.namedtuple('OneResult', ['server', 'time', 'msg', 'txt'])

class GroupedAnswers:
    @staticmethod
    def eval_reply(server_name, dnsreply):
        if not dnsreply.wire:
            msg = None
            txt = '<timeout>'
        else:
            try:
                msg = dns.message.from_wire(dnsreply.wire)
                txt = str(msg)
            except Exception as ex:
                msg = None
                txt = 'failed to parse DNS message: {}'.format(ex)
        return OneResult(server_name, dnsreply.time, msg, txt)

    def __init__(self, criteria, answers):
        self.criteria = criteria
        self.answers = answers
        self.groups = []  # groups of equivalent messages # type: List[List[OneResult]]
        # O(n^2) but n should be fairly small
        for name, dnsreply in self.answers.items():
            reply = self.eval_reply(name, dnsreply)
            match_found = False
            for match_group in self.groups:
                logging.debug('enter group, len(%d)', len(match_group))
                in_group = match_group[0].server
                candidate = reply.server
                diffs = list(diff_pair(self.answers, self.criteria, in_group, candidate))
                if diffs:
                    logging.debug('diff between %s and %s: %s', candidate, in_group, diffs)
                    continue  # try next group
                else:
                    logging.debug('equivalent answer, append')
                    match_group.append(reply)  # found equivalent, done
                    match_found = True
                    break
            if not match_found:
                # no group matched, create a new one
                self.groups.append([reply])

    def __str__(self):
        groups_txt = []
        for group_idx in range(0, len(self.groups)):
            grp_out = []
            group = self.groups[group_idx]
            servers = ', '.join(server.server for server in group)
            grp_out.append('=== group #{} servers {} '.format(group_idx, servers).ljust(78, '='))
            if group_idx != 0:
                grp_out.append('diff against group #0:')
                for diff in diff_pair(
                        self.answers,
                        self.criteria,
                        self.groups[0][0].server, group[0].server):
                    first_val = diff[1].exp_val
                    this_val = diff[1].got_val
                    #if isinstance(this_val, list):
                    #    this_set = set(this_val)
                    #    first_set = set(first_val)
                    #    extra = this_set.difference(first_set)
                    #    missing = first_set.difference(this_set)
                    #    this_val = ''
                    #    for val in extra:
                    #        grp_out.append('+ ' + str(val))
                    #    for val in missing:
                    #        grp_out.append('- ' + str(val))
                    #grp_out.append(' - {field} first={first} this={this}'.format(field=diff[0], first=first_val, this=this_val))
                    if isinstance(this_val, list):
                        first_val = len(first_val)
                        this_val = len(this_val)
                    grp_out.append(
                        ' - {field} first={first} this={this}'.format(
                            field=diff[0], first=first_val, this=this_val))
            grp_out.append(group[0].txt)
            groups_txt.append(grp_out)
        return '\n'.join('\n'.join(grp) for grp in groups_txt)


def main(inargs=None):
    parser = argparse.ArgumentParser(
        description='send one query in parallel to multiple servers, '
                    'receive and compare answers')
    cli.add_arg_config(parser)
    subparsers = parser.add_subparsers(dest='cmd', required=True)

    parser_text = subparsers.add_parser('text',
        help='query specified as text: qname qtype')
    parser_text.add_argument('qname')
    parser_text.add_argument('qtype')

    parser_b64 = subparsers.add_parser('b64url',
        help='query specified as base64url with padding')
    parser_b64.add_argument('base64url')

    args = parser.parse_args(inargs)

    if args.cmd == 'text':
        qname = dns.name.from_text(args.qname)
        qtype = dns.rdatatype.from_text(args.qtype)
        qmsg = dns.message.make_query(qname, qtype, want_dnssec=True)
        qwire = qmsg.to_wire()
    elif args.cmd == 'b64url':
        qwire = base64.urlsafe_b64decode(args.base64url)
    else:
        raise ValueError('unsupported sub-command')

    servers = args.cfg['servers']['names']
    criteria = args.cfg['diff']['criteria']
    sendrecv.module_init(args)
    dnsreplies_factory = DNSRepliesFactory(servers)

    _, packet_blobs = sendrecv.worker_perform_single_query((1, qwire))
    answers = dnsreplies_factory.parse(packet_blobs)
    groups = GroupedAnswers(criteria, answers)
    return groups

if __name__ == "__main__":
    cli.setup_logging(logging.INFO)
    try:
        result = main()
        print(result)
    except KeyboardInterrupt:
        logging.info('SIGINT received, exiting...')
        sys.exit(130)
    except RuntimeError as err:
        logging.error(err)
        sys.exit(1)
