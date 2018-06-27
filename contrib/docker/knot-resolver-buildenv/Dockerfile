FROM ubuntu:latest
MAINTAINER Knot Resolver <knot-resolver@labs.nic.cz>

RUN apt-get update -qq
RUN apt-get upgrade -y -qqq

RUN apt-get install -y -qqq git bsdmainutils build-essential pkg-config libknot-dev libgnutls28-dev liblmdb-dev libluajit-5.1-dev libuv1-dev luajit
