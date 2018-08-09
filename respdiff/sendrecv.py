"""
sendrecv module
===============

This module is used by orchestrator and diffrepro to perform DNS queries in parallel.

The entire module keeps a global state, which enables its easy use with both
threads or processes. Make sure not to break this compatibility.
"""


from argparse import Namespace
import random
import signal
import selectors
import socket
import ssl
import struct
import time
import threading
from typing import Any, Dict, List, Mapping, Sequence, Tuple  # noqa: type hints

import dns.inet
import dns.message

from .database import DNSReply, DNSRepliesFactory
from .typing import ResolverID, QKey, WireFormat

IP = str
IsStreamFlag = bool  # Is message preceeded by RFC 1035 section 4.2.2 length?
Port = int
Protocol = str
ReinitFlag = bool
RepliesBlob = bytes
Selector = selectors.BaseSelector
Socket = socket.socket
ResolverSockets = Sequence[Tuple[ResolverID, Socket, IsStreamFlag]]


# module-wide state variables
__resolvers = []  # type: Sequence[Tuple[ResolverID, IP, Protocol, Port]]
__worker_state = threading.local()
__max_timeouts = 10  # crash when N consecutive timeouts are received from a single resolver
__ignore_timeout = False
__timeout = 10
__time_delay_min = 0
__time_delay_max = 0
__timeout_reply = DNSReply(None)  # optimization: create only one timeout_reply object
__dnsreplies_factory = None


def module_init(args: Namespace) -> None:
    global __resolvers
    global __max_timeouts
    global __ignore_timeout
    global __timeout
    global __time_delay_min
    global __time_delay_max
    global __dnsreplies_factory

    __resolvers = get_resolvers(args.cfg)
    __timeout = args.cfg['sendrecv']['timeout']
    __time_delay_min = args.cfg['sendrecv']['time_delay_min']
    __time_delay_max = args.cfg['sendrecv']['time_delay_max']
    try:
        __max_timeouts = args.cfg['sendrecv']['max_timeouts']
    except KeyError:
        pass
    try:
        __ignore_timeout = args.ignore_timeout
    except AttributeError:
        pass

    servers = [resolver[0] for resolver in __resolvers]
    __dnsreplies_factory = DNSRepliesFactory(servers)


def worker_init() -> None:
    __worker_state.timeouts = {}
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        worker_reinit()
    except RuntimeError as e:
        # silence exception to avoid looping error during multiprocessing pool init
        __worker_state.exception = e


def worker_reinit() -> None:
    selector, sockets = sock_init()  # type: Tuple[Selector, ResolverSockets]
    __worker_state.selector = selector
    __worker_state.sockets = sockets


def worker_deinit() -> None:
    selector = __worker_state.selector
    sockets = __worker_state.sockets

    selector.close()
    for _, sck, _ in sockets:  # type: ignore  # python/mypy#465
        sck.close()


def worker_perform_query(args: Tuple[QKey, WireFormat]) -> Tuple[QKey, RepliesBlob]:
    """DNS query performed by orchestrator"""
    qkey, qwire = args

    try:
        selector = __worker_state.selector
        sockets = __worker_state.sockets
    except AttributeError:
        # handle improper initialization
        raise __worker_state.exception

    # optional artificial delay for testing
    if __time_delay_max > 0:
        time.sleep(random.uniform(__time_delay_min, __time_delay_max))

    replies, reinit = send_recv_parallel(qwire, selector, sockets, __timeout)
    if not __ignore_timeout:
        _check_timeout(replies)

    if reinit:  # a connection is broken or something
        worker_deinit()
        worker_reinit()

    assert __dnsreplies_factory is not None, "Module wasn't initilized!"
    blob = __dnsreplies_factory.serialize(replies)
    return qkey, blob


def worker_perform_single_query(args: Tuple[QKey, WireFormat]) -> Tuple[QKey, RepliesBlob]:
    """Perform a single DNS query with setup and teardown of sockets. Used by diffrepro."""
    qkey, qwire = args
    worker_reinit()
    selector = __worker_state.selector
    sockets = __worker_state.sockets

    replies, _ = send_recv_parallel(qwire, selector, sockets, __timeout)

    worker_deinit()

    assert __dnsreplies_factory is not None, "Module wasn't initilized!"
    blob = __dnsreplies_factory.serialize(replies)
    return qkey, blob


def get_resolvers(
            config: Mapping[str, Any]
        ) -> Sequence[Tuple[ResolverID, IP, Protocol, Port]]:
    resolvers = []
    for resname in config['servers']['names']:
        rescfg = config[resname]
        resolvers.append((resname, rescfg['ip'], rescfg['transport'], rescfg['port']))
    return resolvers


def _check_timeout(replies: Mapping[ResolverID, DNSReply]) -> None:
    for resolver, reply in replies.items():
        timeouts = __worker_state.timeouts
        if not reply.timeout:
            timeouts[resolver] = 0
        else:
            timeouts[resolver] = timeouts.get(resolver, 0) + 1
            if timeouts[resolver] >= __max_timeouts:
                raise RuntimeError(
                    "Resolver '{}' timed-out {:d} times in a row. "
                    "Use '--ignore-timeout' to supress this error.".format(
                        resolver, __max_timeouts))


def sock_init(retry: int = 3) -> Tuple[Selector, Sequence[Tuple[ResolverID, Socket, IsStreamFlag]]]:
    sockets = []
    selector = selectors.DefaultSelector()
    for name, ipaddr, transport, port in __resolvers:
        af = dns.inet.af_for_address(ipaddr)
        if af == dns.inet.AF_INET:
            destination = (ipaddr, port)  # type: Any
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

        # attempt to connect to socket
        attempt = 1
        while attempt <= retry:
            sock = socket.socket(af, socktype, 0)
            if transport == 'tls':
                sock = ssl.wrap_socket(sock)
            try:
                sock.connect(destination)
            except ConnectionRefusedError:  # TCP socket is closed
                raise RuntimeError(
                    "socket: Failed to connect to {dest[0]} port {dest[1]}".format(
                        dest=destination))
            except OSError as exc:
                if exc.errno != 0:
                    raise
                # err=0 often happens during TLS handshake shortly after resolver startup
                time.sleep(attempt)
                attempt += 1
                if attempt > retry:
                    raise RuntimeError(
                        "socket: Failed to connect to {dest[0]} port {dest[1]}".format(
                            dest=destination))
            else:
                break
        sock.setblocking(False)

        sockets.append((name, sock, isstream))
        selector.register(sock, selectors.EVENT_READ, (name, isstream))
    return selector, sockets


def _recv_msg(sock: Socket, isstream: IsStreamFlag) -> WireFormat:
    """Receive DNS message from socket and remove preambule (if present)."""
    if isstream:  # parse preambule
        blength = sock.recv(2)  # TODO: does not work with TLS: , socket.MSG_WAITALL)
        if not blength:  # stream closed
            raise ConnectionError('TCP recv length == 0')
        (length, ) = struct.unpack('!H', blength)
    else:
        length = 65535  # max. UDP message size, no IPv6 jumbograms
    return sock.recv(length)


def send_recv_parallel(
            dgram: WireFormat,  # DNS message suitable for UDP transport
            selector: Selector,
            sockets: ResolverSockets,
            timeout: float
        ) -> Tuple[Mapping[ResolverID, DNSReply], ReinitFlag]:
    replies = {}  # type: Dict[ResolverID, DNSReply]
    streammsg = None
    start_time = time.perf_counter()
    end_time = start_time + timeout
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
        remaining_time = end_time - time.perf_counter()
        if remaining_time <= 0:
            break  # timeout
        events = selector.select(timeout=remaining_time)  # type: ignore  # python/mypy#2070
        for key, _ in events:  # type: ignore  # python/mypy#465
            name, isstream = key.data
            assert isinstance(key.fileobj, socket.socket)  # fileobj can't be int
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
            replies[name] = DNSReply(wire, time.perf_counter() - start_time)

    # set missing replies as timeout
    for resolver, *_ in sockets:  # type: ignore  # python/mypy#465
        if resolver not in replies:
            replies[resolver] = __timeout_reply

    return replies, reinit
