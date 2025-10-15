FROM ubuntu:focal
LABEL org.opencontainers.image.authors="Knot Resolver <knot-resolver@labs.nic.cz>"
ENV DEBIAN_FRONTEND=noninteractive
ARG GIT_TAG

RUN apt-get update
RUN apt-get install -y -qqq git wget build-essential bind9utils libbind-dev libssl-dev libkrb5-dev libcap-dev libxml2-dev libjson-c-dev libgeoip-dev autoconf libtool pkg-config

RUN cd /var/opt; git clone --branch=$GIT_TAG https://github.com/DNS-OARC/dnsperf.git

WORKDIR /var/opt/dnsperf
RUN ./autogen.sh && ./configure && make && make install

ENTRYPOINT ["dnsperf"]
