import dns.message
import dns.rdataclass
import dns.rdatatype
import dns.rrset
import pytest

from qprep import wrk_process_frame, wrk_process_wire_packet


@pytest.mark.parametrize('wire', [
    b'',
    b'x',
    b'xx',
])
def test_wire_input_invalid(wire):
    assert wrk_process_wire_packet((1, wire, 'invalid')) == (1, wire)
    assert wrk_process_wire_packet((1, wire, 'invalid')) == (1, wire)


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
    'something.dotnxdomain.net. A',
    'something.dashnxdomain.net. AAAA',
])
def test_text_input_blacklist(line):
    assert wrk_process_line((1, line, line)) == (None, None)
