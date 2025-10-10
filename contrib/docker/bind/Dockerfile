FROM ubuntu:22.04
LABEL org.opencontainers.image.authors="Knot Resolver <knot-resolver@labs.nic.cz>"

ENV DEBIAN_FRONTEND noninteractive

# list of depedencies copied from https://github.com/google/oss-fuzz/blob/8ac93098b91494264f57771b84f84d65433a9281/projects/bind9/Dockerfile
RUN apt-get -y update && apt-get -y dist-upgrade && \
	apt-get -y install	\
	autoconf		\
	automake		\
	autotools-dev		\
	bison			\
	build-essential		\
	git			\
	libnghttp2-dev		\
	libssl-dev		\
	libtool			\
	libtool-bin		\
	libuv1-dev		\
	liburcu-dev		\
	pkg-config		\
	libcap-dev		\
	libjemalloc-dev		\
	zip && \
	apt-get install -y -qq psmisc linux-tools-generic google-perftools libgoogle-perftools-dev && \
	which named && exit 1 || echo "Ok, no named binary found"

ARG GITLAB_TOKEN
ARG GIT_TAG=v9.20.11
RUN git clone --depth=1 --single-branch --recurse-submodules --shallow-submodules --branch=$GIT_TAG https://gitlab.isc.org/isc-projects/bind9.git /var/opt/bind9 \
	|| git clone --depth=1 --single-branch --recurse-submodules --shallow-submodules --branch=$GIT_TAG https://oauth2:$GITLAB_TOKEN@gitlab.isc.org/isc-private/bind9.git /var/opt/bind9


WORKDIR /var/opt/bind9

RUN autoreconf -fiv

ARG CONFIGUREARGS
ARG CFLAGS
RUN ./configure --disable-doh --prefix=/usr $CONFIGUREARGS
RUN make -j$(nproc)
RUN make install

RUN mkdir /log

ENTRYPOINT ["/var/opt/bind9/bin/named/named", "-c", "/etc/bind9/named.conf", "-f"]
