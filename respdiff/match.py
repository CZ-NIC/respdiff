import collections
import logging
from typing import (  # noqa
    Any, Dict, Hashable, Iterator, Mapping, Optional, Sequence, Tuple)

import dns.rdatatype
from dns.rrset import RRset
import dns.message

from .database import DNSReply
from .typing import FieldLabel, MismatchValue, ResolverID


class DataMismatch(Exception):
    def __init__(self, exp_val: MismatchValue, got_val: MismatchValue) -> None:
        def convert_val_type(val: Any) -> MismatchValue:
            if isinstance(val, str):
                return val
            if isinstance(val, collections.abc.Sequence):
                return [convert_val_type(item) for item in val]
            if isinstance(val, dns.rrset.RRset):
                return str(val)
            logging.warning(
                'DataMismatch: unknown value type (%s), casting to str', type(val),
                stack_info=True)
            return str(val)

        exp_val = convert_val_type(exp_val)
        got_val = convert_val_type(got_val)

        super().__init__(exp_val, got_val)
        if exp_val == got_val:
            raise RuntimeError("exp_val == got_val ({})".format(exp_val))
        self.exp_val = exp_val
        self.got_val = got_val

    @staticmethod
    def format_value(value: MismatchValue) -> str:
        if isinstance(value, list):
            value = ' '.join(value)
        return str(value)

    def __str__(self) -> str:
        return "expected '{}' got '{}'".format(
            self.format_value(self.exp_val),
            self.format_value(self.got_val))

    def __repr__(self) -> str:
        return 'DataMismatch({}, {})'.format(self.exp_val, self.got_val)

    def __eq__(self, other) -> bool:
        return (isinstance(other, DataMismatch)
                and tuple(self.exp_val) == tuple(other.exp_val)
                and tuple(self.got_val) == tuple(other.got_val))

    @property
    def key(self) -> Tuple[Hashable, Hashable]:
        def make_hashable(value):
            if isinstance(value, list):
                value = tuple(value)
            return value

        return (make_hashable(self.exp_val), make_hashable(self.got_val))

    def __hash__(self) -> int:
        return hash(self.key)


def compare_val(exp_val: MismatchValue, got_val: MismatchValue):
    """ Compare values, throw exception if different. """
    if exp_val != got_val:
        raise DataMismatch(str(exp_val), str(got_val))
    return True


def compare_rrs(expected: Sequence[RRset], got: Sequence[RRset]):
    """ Compare lists of RR sets, throw exception if different. """
    for rr in expected:
        if rr not in got:
            raise DataMismatch(expected, got)
    for rr in got:
        if rr not in expected:
            raise DataMismatch(expected, got)
    if len(expected) != len(got):  # detect duplicates
        raise DataMismatch(expected, got)
    return True


def compare_rrs_types(
            exp_val: Sequence[RRset],
            got_val: Sequence[RRset],
            compare_rrsigs: bool):
    """sets of RR types in both sections must match"""
    def rr_ordering_key(rrset):
        return rrset.covers if compare_rrsigs else rrset.rdtype

    def key_to_text(rrtype):
        if not compare_rrsigs:
            return dns.rdatatype.to_text(rrtype)
        return 'RRSIG(%s)' % dns.rdatatype.to_text(rrtype)

    def filter_by_rrsig(seq, rrsig):
        for el in seq:
            el_rrsig = el.rdtype == dns.rdatatype.RRSIG
            if el_rrsig == rrsig:
                yield el

    exp_types = frozenset(rr_ordering_key(rrset)
                          for rrset in filter_by_rrsig(exp_val, compare_rrsigs))
    got_types = frozenset(rr_ordering_key(rrset)
                          for rrset in filter_by_rrsig(got_val, compare_rrsigs))
    if exp_types != got_types:
        raise DataMismatch(
            tuple(key_to_text(i) for i in sorted(exp_types)),
            tuple(key_to_text(i) for i in sorted(got_types)))


def match_part(  # pylint: disable=inconsistent-return-statements
            exp_msg: dns.message.Message,
            got_msg: dns.message.Message,
            criteria: FieldLabel
        ):
    """ Compare scripted reply to given message using single criteria. """
    if criteria == 'opcode':
        return compare_val(exp_msg.opcode(), got_msg.opcode())
    elif criteria == 'flags':
        return compare_val(dns.flags.to_text(exp_msg.flags), dns.flags.to_text(got_msg.flags))
    elif criteria == 'rcode':
        return compare_val(dns.rcode.to_text(exp_msg.rcode()), dns.rcode.to_text(got_msg.rcode()))
    elif criteria == 'question':
        question_match = compare_rrs(exp_msg.question, got_msg.question)
        if not exp_msg.question:  # 0 RRs, nothing else to compare
            return True
        assert len(exp_msg.question) == 1, "multiple question in single DNS query unsupported"
        case_match = compare_val(got_msg.question[0].name.labels, exp_msg.question[0].name.labels)
        return question_match and case_match
    elif criteria in ('answer', 'ttl'):
        return compare_rrs(exp_msg.answer, got_msg.answer)
    elif criteria == 'answertypes':
        return compare_rrs_types(exp_msg.answer, got_msg.answer, compare_rrsigs=False)
    elif criteria == 'answerrrsigs':
        return compare_rrs_types(exp_msg.answer, got_msg.answer, compare_rrsigs=True)
    elif criteria == 'authority':
        return compare_rrs(exp_msg.authority, got_msg.authority)
    elif criteria == 'additional':
        return compare_rrs(exp_msg.additional, got_msg.additional)
    elif criteria == 'edns':
        if got_msg.edns != exp_msg.edns:
            raise DataMismatch(str(exp_msg.edns), str(got_msg.edns))
        if got_msg.payload != exp_msg.payload:
            raise DataMismatch(str(exp_msg.payload), str(got_msg.payload))
    elif criteria == 'nsid':
        nsid_opt = None
        for opt in exp_msg.options:
            if opt.otype == dns.edns.NSID:
                nsid_opt = opt
                break
        # Find matching NSID
        for opt in got_msg.options:
            if opt.otype == dns.edns.NSID:
                if not nsid_opt:
                    raise DataMismatch('', str(opt.data))
                if opt == nsid_opt:
                    return True
                else:
                    raise DataMismatch(str(nsid_opt.data), str(opt.data))
        if nsid_opt:
            raise DataMismatch(str(nsid_opt.data), '')
    else:
        raise NotImplementedError('unknown match request "%s"' % criteria)


def match(
            expected: DNSReply,
            got: DNSReply,
            match_fields: Sequence[FieldLabel]
        ) -> Iterator[Tuple[FieldLabel, DataMismatch]]:
    """ Compare scripted reply to given message based on match criteria. """
    exp_msg, exp_res = expected.parse_wire()
    got_msg, got_res = got.parse_wire()
    exp_malformed = exp_res != DNSReply.WIREFORMAT_VALID
    got_malformed = got_res != DNSReply.WIREFORMAT_VALID

    if expected.timeout or got.timeout:
        if not expected.timeout:
            yield 'timeout', DataMismatch('answer', 'timeout')
        if not got.timeout:
            yield 'timeout', DataMismatch('timeout', 'answer')
    elif exp_malformed or got_malformed:
        if exp_res == got_res:
            logging.warning(
                'match: DNS replies malformed in the same way! (%s)', exp_res)
        else:
            yield 'malformed', DataMismatch(exp_res, got_res)

    if expected.timeout or got.timeout or exp_malformed or got_malformed:
        return  # don't attempt to match any other fields

    # checked above via exp/got_malformed, this is for mypy
    assert exp_msg is not None
    assert got_msg is not None

    for criteria in match_fields:
        try:
            match_part(exp_msg, got_msg, criteria)
        except DataMismatch as ex:
            yield criteria, ex


def diff_pair(
            answers: Mapping[ResolverID, DNSReply],
            criteria: Sequence[FieldLabel],
            name1: ResolverID,
            name2: ResolverID
        ) -> Iterator[Tuple[FieldLabel, DataMismatch]]:
    yield from match(answers[name1], answers[name2], criteria)


def transitive_equality(
            answers: Mapping[ResolverID, DNSReply],
            criteria: Sequence[FieldLabel],
            resolvers: Sequence[ResolverID]
        ) -> bool:
    """
    Compare answers from all resolvers.
    Optimization is based on transitivity of equivalence relation.
    """
    assert len(resolvers) >= 2
    res_a = resolvers[0]  # compare all others to this resolver
    res_others = resolvers[1:]
    return all(map(
        lambda res_b: not any(diff_pair(answers, criteria, res_a, res_b)),
        res_others))


def compare(
            answers: Mapping[ResolverID, DNSReply],
            criteria: Sequence[FieldLabel],
            target: ResolverID
        ) -> Tuple[bool, Optional[Mapping[FieldLabel, DataMismatch]]]:
    others = list(answers.keys())
    try:
        others.remove(target)
    except ValueError:
        return (False, None)  # HACK, target did not reply
    if not others:
        return (False, None)  # HACK, not enough targets to compare
    random_other = others[0]

    if len(others) >= 2:
        # do others agree on the answer?
        others_agree = transitive_equality(answers, criteria, others)
        if not others_agree:
            return (False, None)
    else:
        others_agree = True
    target_diffs = dict(diff_pair(answers, criteria, random_other, target))
    return (others_agree, target_diffs)
