FROM ubuntu:latest
MAINTAINER Knot Resolver <knot-resolver@labs.nic.cz>

CMD ["tail", "-f", "/dev/null"]

RUN apt-get update
RUN apt-get install -y -qqq git wget build-essential bind9utils libbind-dev libssl-dev libkrb5-dev libcap-dev libxml2-dev libjson-c-dev libgeoip-dev

RUN cd /var/opt; git clone https://github.com/akamai/dnsperf.git

WORKDIR /var/opt/dnsperf
RUN ./configure && make && make install

RUN wget -q https://gitlab.labs.nic.cz/knot/respdiff/uploads/9b95b53c04091849023b12b992edad0e/shortlist -O shortlist
