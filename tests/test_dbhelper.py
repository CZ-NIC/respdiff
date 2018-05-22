from respdiff.dbhelper import DNSReply


def test_dns_reply_timeout():
    reply = DNSReply(None)
    assert reply.timeout
    assert reply.time == float('+inf')
