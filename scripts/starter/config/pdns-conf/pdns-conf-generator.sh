#!/bin/bash

ROOT=$(readlink -e $(dirname $(readlink -e "$0")))
IP_ADDR="$1"
PORT="$2"

cat >$ROOT/recursor.conf <<EOL
#################################
# config-dir	Location of configuration directory (recursor.conf)
#
config-dir=/tmp/kresdbench/pdns-conf

#################################
# daemon	Operate as a daemon
#
daemon=yes

#################################
# dnssec	DNSSEC mode: off/process-no-validate (default)/process/log-fail/validate
#
# dnssec=process-no-validate
dnssec=validate

#################################
# local-address	IP addresses to listen on, separated by spaces or commas. Also accepts ports.
#
local-address=$IP_ADDR

#################################
# local-port	port to listen on
#
local-port=$PORT

#################################
# quiet	Suppress logging of questions and answers
#
quiet=yes

#################################
# reuseport	Enable SO_REUSEPORT allowing multiple recursors processes to listen to 1 address
#
reuseport=yes

#################################
# setgid	If set, change group id to this gid for more security
#
setgid=kresdbench

#################################
# setuid	If set, change user id to this uid for more security
#
setuid=kresdbench

#################################
# socket-dir    Where the controlsocket will live, /var/run when unset and not chrooted
#
socket-dir=/home/kresdbench

#################################
# socket-group	Group of socket
#
socket-group=kresdbench

#################################
# socket-owner	Owner of socket
#
socket-owner=kresdbench

#################################
# threads	Launch this number of threads
#
threads=1

#################################
# write-pid	Write a PID file
#
# write-pid=yes
EOL
echo "OK"
exit 0
