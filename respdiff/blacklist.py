import dpkt
import dns

from dns.message import Message, from_wire


def extract_packet(packet: bytes) -> Message:
    """
    Extract packet from bytes. Return dns.Message
    """
    frame = dpkt.ethernet.Ethernet(packet)
    ip = frame.data
    transport = ip.data
    if transport.data == b'':
        return True
    if isinstance(transport, dpkt.tcp.TCP):
        wire = transport.data[2:]
    else:
        wire = transport.data
    dnsmsg = from_wire(wire)
    return dnsmsg


def is_blacklisted(packet: bytes) -> bool:
    """
    Detect if given packet is blacklisted or not.
    """
    try:
        dnsmsg = extract_packet(packet)
        flags = dns.flags.to_text(dnsmsg.flags).split()
        if 'QR' in flags:  # not a query
            return True
        dnspacket = dnsmsg.question[0]
        # there is not standard describing common behavior for ANY query
        if dnspacket.rdtype == dns.rdatatype.ANY:
            return True
        return False
    except Exception:
        return False
