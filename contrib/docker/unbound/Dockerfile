FROM ubuntu:focal
LABEL org.opencontainers.image.authors="Knot Resolver <knot-resolver@labs.nic.cz>"
ARG GIT_TAG
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -qq
RUN apt-get upgrade -y -qqq
RUN apt-get install -y -qqq build-essential git make wget libssl-dev libexpat1-dev libevent-dev libnghttp2-dev

RUN git clone --depth 1 --branch=$GIT_TAG https://github.com/NLnetLabs/unbound.git /var/opt/unbound
WORKDIR /var/opt/unbound
RUN ./configure --with-libevent --with-libnghttp2
RUN make
RUN make install

RUN useradd -s /usr/sbin/nologin -r unbound

ENTRYPOINT ["/var/opt/unbound/unbound", "-d"]
