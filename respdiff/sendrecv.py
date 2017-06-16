import os
import selectors
import socket

import dns.inet
import dns.message

def sock_init(resolvers):
    """
    resolvers: [(name, ipaddr, port)]
    returns (selector, [(name, socket, sendtoarg)])
    """
    sockets = []
    selector = selectors.DefaultSelector()
    for name, ipaddr, port in resolvers:
        af = dns.inet.af_for_address(ipaddr)
        if af == dns.inet.AF_INET:
            destination = (ipaddr, port)
        elif af == dns.inet.AF_INET6:
            destination = (ipaddr, port, 0, 0)
        else:
            raise NotImplementedError('AF')
        sock = socket.socket(af, socket.SOCK_DGRAM, 0)
        sock.setblocking(False)
        sockets.append((name, sock, destination))
        selector.register(sock, selectors.EVENT_READ, name)
    # selector.close() ?  # TODO
    return selector, sockets

def send_recv_parallel(what, selector, sockets, timeout):
    replies = {}
    for _, sock, destination in sockets:
        sock.sendto(what, destination)

    # receive replies
    while len(replies) != len(sockets):
        events = selector.select(timeout=timeout)  # BLEH! timeout shortening
        for key, _ in events:
            name = key.data
            sock = key.fileobj
            (wire, from_address) = sock.recvfrom(65535)
            #assert len(wire) > 14
            if what[0:2] != wire[0:2]:
                continue  # wrong msgid, this might be a delayed answer - ignore it
            replies[name] = wire
        if not events:
            break  # TIMEOUT

    return replies
