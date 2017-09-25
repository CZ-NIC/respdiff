import dns.rdatatype


def obj_blacklisted(msg):
    """
    Detect blacklisted DNS message objects.
    """
    if len(msg.question) >= 1:
        if msg.question[0].rdtype == dns.rdatatype.ANY:
            return True
    return False
