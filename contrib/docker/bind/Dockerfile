FROM ubuntu:latest
MAINTAINER Knot Resolver <knot-resolver@labs.nic.cz>
ARG GIT_TAG=v9_13_4

RUN apt-get update -qq
RUN apt-get upgrade -y -qqq

RUN apt-get install -y -qqq git build-essential make libssl-dev python3 python3-ply python3-dnspython

RUN git clone --depth 1 --branch=$GIT_TAG https://gitlab.isc.org/isc-projects/bind9.git /var/opt/bind9
WORKDIR /var/opt/bind9
RUN ./configure --disable-backtrace --disable-symtable --with-libtool --enable-full-report --without-lmdb --without-zlib --without-gssapi --without-libxml2 --without-dlopen --disable-linux-caps
RUN make

ENTRYPOINT ["/var/opt/bind9/bin/named/named", "-c", "/etc/bind9/named.conf", "-f"]
