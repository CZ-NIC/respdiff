FROM ubuntu:focal
LABEL org.opencontainers.image.authors="Knot Resolver <knot-resolver@labs.nic.cz>"
ARG GIT_TAG
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq
RUN apt-get upgrade -y -qqq

RUN apt-get install -y -qqq git build-essential make autoconf libtool libboost-dev libboost-serialization-dev libboost-system-dev libboost-thread-dev libboost-context-dev libssl-dev g++ pkg-config libluajit-5.1-dev libgnutls28-dev bison flex ragel curl libedit-dev libh2o-evloop-dev python3-virtualenv

RUN git clone --depth 1 --branch=$GIT_TAG https://github.com/PowerDNS/pdns.git /var/opt/powerdns

WORKDIR /var/opt/powerdns/pdns/dnsdistdist
RUN autoreconf -vi
RUN ./configure --enable-dns-over-tls --enable-dns-over-https
RUN make -j8

ENTRYPOINT ["/var/opt/powerdns/pdns/dnsdistdist/dnsdist", "-C", "/etc/dnsdist/dnsdist.conf", "--supervised"]
