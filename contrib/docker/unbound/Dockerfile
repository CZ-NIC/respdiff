FROM ubuntu:focal
MAINTAINER Knot Resolver <knot-resolver@labs.nic.cz>
ARG UNBOUND_VERSION
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq
RUN apt-get upgrade -y -qqq
RUN apt-get install -y -qqq build-essential make wget libssl-dev libexpat1-dev libevent-dev

RUN wget -O /tmp/unbound.tar.gz https://unbound.net/downloads/unbound-$UNBOUND_VERSION.tar.gz
RUN cd /tmp && tar -xzvf unbound.tar.gz && mv unbound-* /var/opt/unbound

WORKDIR /var/opt/unbound
RUN ./configure --with-libevent
RUN make
RUN make install

RUN useradd -s /usr/sbin/nologin -r unbound

ENTRYPOINT ["/var/opt/unbound/unbound", "-d"]
