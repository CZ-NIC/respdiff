FROM ubuntu:latest
MAINTAINER Knot Resolver <knot-resolver@labs.nic.cz>
ARG GIT_TAG

RUN apt-get update
RUN apt-get install -y -qqq git wget build-essential bind9utils libbind-dev libssl-dev libkrb5-dev libcap-dev libxml2-dev libjson-c-dev libgeoip-dev autoconf libtool

RUN cd /var/opt; git clone --branch=$GIT_TAG https://github.com/akamai/dnsperf.git

WORKDIR /var/opt/dnsperf
RUN ./autogen.sh && ./configure && make && make install

ENTRYPOINT ["dnsperf"]
