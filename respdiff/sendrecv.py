"""
sendrecv module
===============

This module is used by orchestrator and diffrepro to perform DNS queries in parallel.

The entire module keeps a global state, which enables its easy use with both
threads or processes. Make sure not to break this compatibility.
"""

from argparse import Namespace
import logging
import random
import signal
import selectors
import socket
import ssl
import struct
import time
import threading
from typing import (
    Any,
    Dict,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)  # noqa: type hints

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
__max_timeouts = (
    10  # crash when N consecutive timeouts are received from a single resolver
)
__ignore_timeout = False
__timeout = 16
__time_delay_min = 0
__time_delay_max = 0
__timeout_reply = DNSReply(None)  # optimization: create only one timeout_reply object
__dnsreplies_factory = None


CONN_RESET_RETRIES = 2


class TcpDnsLengthError(ConnectionError):
    pass


class ResolverConnectionError(ConnectionError):
    def __init__(self, resolver: ResolverID, message: str):
        super().__init__(message)
        self.resolver = resolver

    def __str__(self):
        return f"[{self.resolver}] {super().__str__()}"


def module_init(args: Namespace) -> None:
    global __resolvers
    global __max_timeouts
    global __ignore_timeout
    global __timeout
    global __time_delay_min
    global __time_delay_max
    global __dnsreplies_factory

    __resolvers = get_resolvers(args.cfg)
    __timeout = args.cfg["sendrecv"]["timeout"]
    __time_delay_min = args.cfg["sendrecv"]["time_delay_min"]
    __time_delay_max = args.cfg["sendrecv"]["time_delay_max"]
    try:
        __max_timeouts = args.cfg["sendrecv"]["max_timeouts"]
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

    # optional artificial delay for testing
    if __time_delay_max > 0:
        time.sleep(random.uniform(__time_delay_min, __time_delay_max))

    replies = send_recv_parallel(qwire, __timeout)

    if not __ignore_timeout:
        _check_timeout(replies)

    assert __dnsreplies_factory is not None, "Module wasn't initilized!"
    blob = __dnsreplies_factory.serialize(replies)
    return qkey, blob


def worker_perform_single_query(
    args: Tuple[QKey, WireFormat]
) -> Tuple[QKey, RepliesBlob]:
    """Perform a single DNS query with setup and teardown of sockets. Used by diffrepro."""
    qkey, qwire = args
    worker_reinit()

    replies = send_recv_parallel(qwire, __timeout, reinit_on_tcpfin=False)

    worker_deinit()

    assert __dnsreplies_factory is not None, "Module wasn't initilized!"
    blob = __dnsreplies_factory.serialize(replies)
    return qkey, blob


def get_resolvers(
    config: Mapping[str, Any]
) -> Sequence[Tuple[ResolverID, IP, Protocol, Port]]:
    resolvers = []
    for resname in config["servers"]["names"]:
        rescfg = config[resname]
        resolvers.append((resname, rescfg["ip"], rescfg["transport"], rescfg["port"]))
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
                        resolver, __max_timeouts
                    )
                )


def make_ssl_context():
    # TLS v1.3 support might not be complete as of Python 3.7.2 and there
    # seem to be issues when using it in respdiff.
    # https://docs.python.org/3/library/ssl.html#tls-1-3

    # NOTE forcing TLS v1.2 is hacky, because of different py3/openssl versions...
    if getattr(ssl, "PROTOCOL_TLS", None) is not None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS)  # pylint: disable=no-member
    else:
        context = ssl.SSLContext()

    if getattr(ssl, "maximum_version", None) is not None:
        context.maximum_version = ssl.TLSVersion.TLSv1_2  # pylint: disable=no-member
    else:
        context.options |= ssl.OP_NO_SSLv2
        context.options |= ssl.OP_NO_SSLv3
        context.options |= ssl.OP_NO_TLSv1
        context.options |= ssl.OP_NO_TLSv1_1
        if getattr(ssl, "OP_NO_TLSv1_3", None) is not None:
            context.options |= ssl.OP_NO_TLSv1_3  # pylint: disable=no-member

    # turn off certificate verification
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    return context


def sock_init(
    retry: int = 3,
) -> Tuple[Selector, Sequence[Tuple[ResolverID, Socket, IsStreamFlag]]]:
    sockets = []
    selector = selectors.DefaultSelector()
    for name, ipaddr, transport, port in __resolvers:
        af = dns.inet.af_for_address(ipaddr)
        if af == dns.inet.AF_INET:
            destination = (ipaddr, port)  # type: Any
        elif af == dns.inet.AF_INET6:
            destination = (ipaddr, port, 0, 0)
        else:
            raise NotImplementedError("AF")

        if transport in {"tcp", "tls"}:
            socktype = socket.SOCK_STREAM
            isstream = True
        elif transport == "udp":
            socktype = socket.SOCK_DGRAM
            isstream = False
        else:
            raise NotImplementedError("transport: {}".format(transport))

        # attempt to connect to socket
        attempt = 1
        while attempt <= retry:
            sock = socket.socket(af, socktype, 0)
            if transport == "tls":
                ctx = make_ssl_context()
                sock = ctx.wrap_socket(sock)
            try:
                sock.connect(destination)
            except ConnectionRefusedError as e:  # TCP socket is closed
                raise RuntimeError(
                    "socket: Failed to connect to {dest[0]} port {dest[1]}".format(
                        dest=destination
                    )
                ) from e
            except OSError as exc:
                if exc.errno != 0 and not isinstance(exc, ConnectionResetError):
                    raise
                # err=0 often happens during TLS handshake shortly after resolver startup
                # ConnectionResetError tends to happen for diffrepro TLS connections
                time.sleep(attempt)
                attempt += 1
                if attempt > retry:
                    raise RuntimeError(
                        "socket: Failed to connect to {dest[0]} port {dest[1]}".format(
                            dest=destination
                        )
                    ) from exc
            else:
                break
        sock.setblocking(False)

        sockets.append((name, sock, isstream))
        selector.register(sock, selectors.EVENT_READ, (name, isstream))
    return selector, sockets


def _recv_msg(sock: Socket, isstream: IsStreamFlag) -> WireFormat:
    """Receive DNS message from socket and remove preambule (if present)."""
    if isstream:  # parse preambule
        try:
            blength = sock.recv(2)
        except ssl.SSLWantReadError as e:
            raise TcpDnsLengthError("failed to recv DNS packet length") from e
        if len(blength) != 2:  # FIN / RST
            raise TcpDnsLengthError("failed to recv DNS packet length")
        (length,) = struct.unpack("!H", blength)
    else:
        length = 65535  # max. UDP message size, no IPv6 jumbograms
    return sock.recv(length)


def _create_sendbuf(dnsdata: WireFormat, isstream: IsStreamFlag) -> bytes:
    if isstream:  # prepend length, RFC 1035 section 4.2.2
        length = len(dnsdata)
        return struct.pack("!H", length) + dnsdata
    return dnsdata


def _get_resolver_from_sock(
    sockets: ResolverSockets, sock: Socket
) -> Optional[ResolverID]:
    for resolver, resolver_sock, _ in sockets:
        if sock == resolver_sock:
            return resolver
    return None


def _recv_from_resolvers(
    selector: Selector, sockets: ResolverSockets, msgid: bytes, timeout: float
) -> Tuple[Dict[ResolverID, DNSReply], bool]:

    def raise_resolver_exc(sock, exc):
        resolver = _get_resolver_from_sock(sockets, sock)
        if resolver is not None:
            raise ResolverConnectionError(resolver, str(exc)) from exc
        raise exc

    start_time = time.perf_counter()
    end_time = start_time + timeout
    replies = {}  # type: Dict[ResolverID, DNSReply]
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
            except TcpDnsLengthError as exc:
                if name in replies:  # we have a reply already, most likely TCP FIN
                    reinit = True
                    selector.unregister(sock)
                    continue  # receive answers from other parties
                # no reply -> raise error
                raise_resolver_exc(sock, exc)
            except ConnectionError as exc:
                raise_resolver_exc(sock, exc)
            if msgid != wire[0:2]:
                continue  # wrong msgid, this might be a delayed answer - ignore it
            replies[name] = DNSReply(wire, time.perf_counter() - start_time)

    return replies, reinit


def _send_recv_parallel(
    dgram: WireFormat,  # DNS message suitable for UDP transport
    selector: Selector,
    sockets: ResolverSockets,
    timeout: float,
) -> Tuple[Mapping[ResolverID, DNSReply], ReinitFlag]:
    # send queries
    for resolver, sock, isstream in sockets:
        sendbuf = _create_sendbuf(dgram, isstream)
        try:
            sock.sendall(sendbuf)
        except ConnectionError as exc:
            raise ResolverConnectionError(resolver, str(exc)) from exc

    # receive replies
    msgid = dgram[0:2]
    replies, reinit = _recv_from_resolvers(selector, sockets, msgid, timeout)

    # set missing replies as timeout
    for resolver, *_ in sockets:  # type: ignore  # python/mypy#465
        if resolver not in replies:
            replies[resolver] = __timeout_reply

    return replies, reinit


def send_recv_parallel(
    dgram: WireFormat,  # DNS message suitable for UDP transport
    timeout: float,
    reinit_on_tcpfin: bool = True,
) -> Mapping[ResolverID, DNSReply]:
    problematic = []
    for _ in range(CONN_RESET_RETRIES + 1):
        try:  # get sockets and selector
            selector = __worker_state.selector
            sockets = __worker_state.sockets
        except AttributeError as e:
            # handle improper initialization
            raise __worker_state.exception from e

        try:
            replies, reinit = _send_recv_parallel(dgram, selector, sockets, timeout)
            if reinit_on_tcpfin and reinit:  # a connection is closed
                worker_deinit()
                worker_reinit()
            return replies
        # The following exception handling is typically triggered by TCP RST,
        # but it could also indicate some issue with one of the resolvers.
        except ResolverConnectionError as exc:
            problematic.append(exc.resolver)
            logging.debug(exc)
            worker_deinit()  # re-establish connection
            worker_reinit()
        except ConnectionError as exc:  # most likely TCP RST
            logging.debug(exc)
            worker_deinit()  # re-establish connection
            worker_reinit()
    raise RuntimeError(
        "ConnectionError received {} times in a row ({}), exiting!".format(
            CONN_RESET_RETRIES + 1, ", ".join(problematic)
        )
    )
