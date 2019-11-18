#!/bin/bash

export ASAN_OPTIONS=disable_coredump=0,abort_on_error=1

exec /var/opt/knot-resolver/.install/sbin/kresd -c /etc/knot-resolver/kresd.conf -v -f 1 /dev/shm >> /log/kresd.log
