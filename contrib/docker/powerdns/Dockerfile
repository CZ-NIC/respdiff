FROM ubuntu:latest
MAINTAINER Knot Resolver <knot-resolver@labs.nic.cz>
ARG GIT_TAG

RUN apt-get update -qq
RUN apt-get upgrade -y -qqq
RUN apt-get install -y -qqq git build-essential make autoconf libtool libboost-dev libboost-serialization-dev libboost-system-dev libboost-thread-dev libboost-context-dev libssl-dev g++ make pkg-config libluajit-5.1-dev bison flex ragel curl python-virtualenv

RUN git clone --depth 1 --branch=$GIT_TAG https://github.com/PowerDNS/pdns.git /var/opt/powerdns

WORKDIR /var/opt/powerdns/pdns/recursordist
RUN autoreconf -vi
RUN ./configure
RUN make

ENTRYPOINT ["/var/opt/powerdns/pdns/recursordist/pdns_recursor"]
