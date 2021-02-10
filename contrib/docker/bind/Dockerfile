FROM ubuntu:20.04
MAINTAINER Petr Špaček <pspacek@isc.org>

ENV DEBIAN_FRONTEND noninteractive

# list of depedencies copied from https://github.com/google/oss-fuzz/blob/8ac93098b91494264f57771b84f84d65433a9281/projects/bind9/Dockerfile
RUN apt-get -y update && apt-get -y dist-upgrade
RUN apt-get -y install		\
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
	pkg-config		\
	zip

RUN apt-get install -y -qq psmisc linux-tools-generic google-perftools libgoogle-perftools-dev

# guard against pulling in named binary accidentally
RUN which named && exit 1 || echo "Ok, no named binary found"

ARG GITLAB_TOKEN
ARG GIT_TAG=main
RUN git clone --depth=1 --single-branch --recurse-submodules --shallow-submodules --branch=$GIT_TAG https://gitlab.isc.org/isc-projects/bind9.git /var/opt/bind9 \
	|| git clone --depth=1 --single-branch --recurse-submodules --shallow-submodules --branch=$GIT_TAG https://oauth2:$GITLAB_TOKEN@gitlab.isc.org/isc-private/bind9.git /var/opt/bind9


WORKDIR /var/opt/bind9

RUN autoreconf -fiv

ARG CONFIGUREARGS
ARG CFLAGS
RUN ./configure --without-python --disable-linux-caps --prefix=/usr $CONFIGUREARGS
RUN make -j$(nproc)
RUN make install

RUN mkdir /log
