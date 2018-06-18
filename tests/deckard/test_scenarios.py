from respdiff.database import DNSReply
from respdiff.match import DataMismatch

from .util import diffsum_toolchain


@diffsum_toolchain('malformed.rpl')
def test_malformed(report):
    fcs = report.summary.get_field_counters()
    assert len(report.target_disagreements) == 5
    assert fcs['malformed'][DataMismatch(DNSReply.WIREFORMAT_VALID, 'FormError')] == 1
    assert fcs['malformed'][DataMismatch(DNSReply.WIREFORMAT_VALID, 'ShortHeader')] == 1
    assert fcs['malformed'][DataMismatch(DNSReply.WIREFORMAT_VALID, 'TrailingJunk')] == 2
    assert sum(fcs['timeout'].values()) == 1
