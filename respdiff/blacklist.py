import dns

from dns.message import Message

_BLACKLIST_SUBDOMAINS = [dns.name.from_text(name) for name in [
    'local.',
    # dotnxdomain.net and dashnxdomain.net are used by APNIC for ephemeral
    # single-query tests so there is no point in asking these repeatedly
    'dotnxdomain.net.', 'dashnxdomain.net.',
    # Some malware names from shadowserver.org
    # Asking them repeatedly may give impression that we're infected.
    'ak-is.net', 'boceureid.com', 'dkfdbbtmeeow.net', 'dssjistyyqhs.online',
    'gowwmcawjbuwrvrwc.com', 'hhjxobtybumg.pw', 'iqodqxy.info', 'k5service.org',
    'kibot.pw', 'mdtrlvfjppreyv.in', 'oxekbtumwc.info', 'raz4756pi7zop.com',
    'rbqfe.net', 'theyardservice.com', 'uwnlzvl.info', 'weg11uvrym3.com',
    'winsrw.com', 'xfwnbk.info', 'xmrimtl.net',
]]


def is_blacklisted(dnsmsg: Message) -> bool:
    """
    Detect if given packet is blacklisted or not.
    """
    try:
        flags = dns.flags.to_text(dnsmsg.flags).split()
        if 'QR' in flags:  # not a query
            return True
        if len(dnsmsg.question) != 1:
            # weird but valid packet (maybe DNS Cookies)
            return False
        question = dnsmsg.question[0]
        # there is not standard describing common behavior for ANY/RRSIG query
        if question.rdtype in {dns.rdatatype.ANY, dns.rdatatype.RRSIG}:
            return True
        return any(question.name.is_subdomain(name)
                   for name in _BLACKLIST_SUBDOMAINS)
    except Exception:
        # weird stuff, it's better to test resolver with this as well!
        return False
