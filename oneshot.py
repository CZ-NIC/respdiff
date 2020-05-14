#!/usr/bin/env python3

import argparse
import base64
import collections
import logging
import os
from pathlib import Path
import sys

import dns.name
import dns.rdatatype
import dns.message

from respdiff import cli, sendrecv
from respdiff.database import DNSRepliesFactory, DNSReply
from respdiff.match import diff_pair, match


class OneResult:
    def __init__(self, server: str, dnsreply: DNSReply):
        self.server = server
        self.replyobj = dnsreply
        if not dnsreply.wire:
            self.msg = None
            self.txt = '<timeout>'
        else:
            try:
                self.msg = dns.message.from_wire(dnsreply.wire)
                self.txt = str(self.msg)
            except Exception as ex:
                self.msg = None
                self.txt = 'failed to parse DNS message: {}'.format(ex)

    def __str__(self):
        return self.txt

    def export(self, outdir):
        with open(Path(outdir) / Path(f'{self.server}.txt') , 'w') as f_txt:
            f_txt.write(self.txt)
        if self.replyobj.wire:
            with open(Path(outdir) / Path(f'{self.server}.wire'), 'wb') as f_w:
                f_w.write(self.replyobj.wire)

class OneGroup:
    def __init__(self, criteria, first_result):
        self.criteria = criteria
        self.equivalent = [first_result]

    @property
    def servers(self):
        return ', '.join(result.server for result in self.equivalent)

    def __str__(self):
        out = []
        out.append('servers {} '.format(self.servers))
        out.append(str(self.equivalent[0]))
        return '\n'.join(out)

    def diff(self, outgroup_result):
        yield from match(self.equivalent[0].replyobj,
                         outgroup_result.replyobj,
                         self.criteria)

    #out.append('= diff against group #0:')
    def diff_str(self, outgroup_result):
        out = []
        for diff in self.diff(outgroup_result):
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
                first_val = '{} rrs'.format(len(first_val))
                this_val = '{} rrs'.format(len(this_val))
            out.append(
                ' - {field} first={first} this={this}'.format(
                    field=diff[0], first=first_val, this=this_val))
        return '\n'.join(out)


    def append_if_equivalent(self, new_result: OneResult):
        # match() actually returns mismatches ...
        if any(self.diff(new_result)):
            return False
        else:  # equivalent
            self.equivalent.append(new_result)
            return True

    def export(self, outdir):
        for result in self.equivalent:
            result.export(outdir)


class GroupedAnswers:
    """
    Groups of equivalent DNS messages.
    """
    def __init__(self, criteria, answers):
        self.criteria = criteria
        self.groups = []  # groups of equivalent messages # type: List[OneGroup]
        # O(n^2) but n should be fairly small
        from IPython.core.debugger import set_trace
        for name, dnsreply in answers.items():
            #set_trace()
            new_result = OneResult(name, dnsreply)
            match_found = False
            for match_group in self.groups:
                if not match_group.append_if_equivalent(new_result):
                    continue  # try next group
                match_found = True
                break
            if not match_found:
                # no group matched, create a new one
                self.groups.append(OneGroup(criteria, new_result))

    def __str__(self):
        out = []
        base_group = self.groups[0]
        for group_idx in range(0, len(self.groups)):
            group = self.groups[group_idx]
            if group != base_group:
                diff_str = base_group.diff_str(group.equivalent[0])
                out.append(f'=== group #{group_idx} differs in:')
                out.append(diff_str)
            else:
                out.append(f'=== group #{group_idx}:')
            out.append(str(group))
        return '\n'.join(out)

    def export(self, outdir):
        for group in self.groups:
            group.export(outdir)

def main(inargs=None):
    parser = argparse.ArgumentParser(
        description='send one query in parallel to multiple servers, '
                    'receive and compare answers')
    cli.add_arg_config(parser)
    parser.add_argument('--output-dir')
    subparsers = parser.add_subparsers(dest='cmd', required=True)

    parser_text = subparsers.add_parser('text',
        help='query specified as text: qname qtype')
    parser_text.add_argument('qname')
    parser_text.add_argument('qtype')

    parser_b64 = subparsers.add_parser('b64url',
        help='query specified as base64url with padding')
    parser_b64.add_argument('base64url')

    args = parser.parse_args(inargs)

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)

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

    if args.output_dir:
        groups.export(args.output_dir)
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
