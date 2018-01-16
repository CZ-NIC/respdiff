import selectors
import socket
import ssl
import struct
import time
from typing import Dict

import dns.inet
import dns.message

import dataformat


TIMEOUT_REPLIES = {}  # type: Dict[int, dataformat.Reply]


def sock_init(resolvers):
    """
    resolvers: [(name, ipaddr, transport, port)]
    returns (selector, [(name, socket, isstream)])
    """
    sockets = []
    selector = selectors.DefaultSelector()
    for name, ipaddr, transport, port in resolvers:
        af = dns.inet.af_for_address(ipaddr)
        if af == dns.inet.AF_INET:
            destination = (ipaddr, port)
        elif af == dns.inet.AF_INET6:
            destination = (ipaddr, port, 0, 0)
        else:
            raise NotImplementedError('AF')

        if transport in {'tcp', 'tls'}:
            socktype = socket.SOCK_STREAM
            isstream = True
        elif transport == 'udp':
            socktype = socket.SOCK_DGRAM
            isstream = False
        else:
            raise NotImplementedError('transport: {}'.format(transport))
        sock = socket.socket(af, socktype, 0)
        if transport == 'tls':
            sock = ssl.wrap_socket(sock)
        sock.connect(destination)
        sock.setblocking(False)

        sockets.append((name, sock, isstream))
        selector.register(sock, selectors.EVENT_READ, (name, isstream))
    # selector.close() ?  # TODO
    return selector, sockets


def _recv_msg(sock, isstream):
    """
    receive DNS message from socket
    issteam: Is message preceeded by RFC 1035 section 4.2.2 length?
    returns: wire format without preambule or ConnectionError
    """
    if isstream:  # parse preambule
        blength = sock.recv(2)  # TODO: does not work with TLS: , socket.MSG_WAITALL)
        if len(blength) == 0:  # stream closed
            raise ConnectionError('TCP recv length == 0')
        (length, ) = struct.unpack('!H', blength)
    else:
        length = 65535  # max. UDP message size, no IPv6 jumbograms
    return sock.recv(length)


def send_recv_parallel(dgram, selector, sockets, timeout):
    """
    dgram: DNS message in binary format suitable for UDP transport
    """
    replies = {}
    streammsg = None
    # optimization: create only one timeout_reply object per timeout value
    timeout_reply = TIMEOUT_REPLIES.setdefault(timeout, dataformat.Reply(None, timeout))
    start_time = time.perf_counter()
    for _, sock, isstream in sockets:
        if isstream:  # prepend length, RFC 1035 section 4.2.2
            if not streammsg:
                length = len(dgram)
                streammsg = struct.pack('!H', length) + dgram
            sock.sendall(streammsg)
        else:
            sock.sendall(dgram)

    # receive replies
    reinit = False
    while len(replies) != len(sockets):
        events = selector.select(timeout=timeout)  # BLEH! timeout shortening
        for key, _ in events:
            name, isstream = key.data
            sock = key.fileobj
            try:
                wire = _recv_msg(sock, isstream)
            except ConnectionError:
                reinit = True
                selector.unregister(sock)
                continue  # receive answers from other parties
            # assert len(wire) > 14
            if dgram[0:2] != wire[0:2]:
                continue  # wrong msgid, this might be a delayed answer - ignore it
            replies[name] = dataformat.Reply(wire, time.perf_counter() - start_time)
        if not events:
            break  # TIMEOUT

    # set missing replies as timeout
    for resolver, *_ in sockets:
        if resolver not in replies:
            replies[resolver] = timeout_reply

    return replies, reinit
