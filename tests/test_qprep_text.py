import dns.message
import dns.rdataclass
import dns.rdatatype
import dns.rrset
import pytest

from qprep import wrk_process_line


@pytest.mark.parametrize('line', [
    '',
    'x'*256 + ' A',
    '\123x.test. 65536',
    '\321.test. 1',
    'test. A,AAAA',
    'test. A, AAAA',
])
def test_text_input_invalid(line):
    assert wrk_process_line((1, line, line)) == (None, None)


@pytest.mark.parametrize('qname, qtype', [
    ('x', 'A'),
    ('x', 1),
    ('blabla.test.', 'TSIG'),
])
def test_text_input_valid(qname, qtype):
    line = '{} {}'.format(qname, qtype)

    if isinstance(qtype, int):
        rdtype = qtype
    else:
        rdtype = dns.rdatatype.from_text(qtype)
    expected = [dns.rrset.RRset(dns.name.from_text(qname), dns.rdataclass.IN, rdtype)]

    qid, wire = wrk_process_line((1, line, line))
    msg = dns.message.from_wire(wire)
    assert msg.question == expected
    assert qid == 1


@pytest.mark.parametrize('line', [
    'test. ANY',
    'test. RRSIG',
    'dotnxdomain.net. 28',
    'something.dotnxdomain.net. A',
    'something.dashnxdomain.net. AAAA',
])
def test_text_input_blacklist(line):
    assert wrk_process_line((1, line, line)) == (None, None)
