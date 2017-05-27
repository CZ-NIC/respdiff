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
    #print(sockets)
    return selector, sockets

def send_recv_parallel(what, selector, sockets, timeout):
    replies = []
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
            replies.append((name, wire))
        if not events:
            break  # TIMEOUT

    return replies

def worker_init(resolvers, init_timeout):
    global selector
    global sockets
    global timeout
    timeout = init_timeout
    selector, sockets = sock_init(resolvers)

def query_resolvers(workdir):
    global selector
    global sockets
    global timeout

    qfilename = os.path.join(workdir, 'q.dns')
    #print(qfilename)
    with open(qfilename, 'rb') as qfile:
        qwire = qfile.read()
    replies = send_recv_parallel(qwire, selector, sockets, timeout)
    for answer in replies:
        afilename = os.path.join(workdir, "%s.dns" % answer[0])
        with open(afilename, 'wb') as afile:
            afile.write(answer[1])
    #print('%s DONE' % qfilename)
