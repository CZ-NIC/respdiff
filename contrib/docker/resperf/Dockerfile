FROM ubuntu:focal
MAINTAINER Knot Resolver <knot-resolver@labs.nic.cz>

RUN apt-get update
RUN apt-get install -y -qqq git wget build-essential bind9utils libbind-dev libssl-dev libkrb5-dev libcap-dev libxml2-dev libjson-c-dev libgeoip-dev libnghttp2-dev

RUN cd /var/opt; git clone https://github.com/DNS-OARC/dnsperf.git

WORKDIR /var/opt/dnsperf
RUN ./configure && make && make install

RUN wget -q https://gitlab.nic.cz/knot/respdiff/uploads/45c21d26fb1c1c06cb00f0aeb34742c7/shortlist3 -O shortlist

ENTRYPOINT ["resperf"]
