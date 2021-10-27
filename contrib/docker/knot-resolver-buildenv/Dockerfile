FROM ubuntu:21.10
MAINTAINER Knot Resolver <knot-resolver@labs.nic.cz>
ARG KNOT_BRANCH
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq
RUN apt-get upgrade -y -qqq

# Install Knot DNS from sources
RUN apt-get -y -qqq install git-core make gcc libtool autoconf pkg-config \
	liburcu-dev liblmdb-dev libgnutls28-dev libjansson-dev libedit-dev \
	libidn11-dev libnghttp2-dev libelf-dev libbpf-dev libmnl-dev
RUN git clone -b $KNOT_BRANCH --depth=1 https://gitlab.nic.cz/knot/knot-dns.git /tmp/knot
WORKDIR /tmp/knot
RUN autoreconf -if
RUN ./configure --disable-static --disable-fastparser --disable-documentation
RUN make
RUN make install
RUN ldconfig

# Knot Resolver dependencies
RUN apt-get install -y -qqq git bsdmainutils build-essential pkg-config \
	libgnutls28-dev liblmdb-dev libluajit-5.1-dev libuv1-dev libnghttp2-dev \
	luajit meson gdb
