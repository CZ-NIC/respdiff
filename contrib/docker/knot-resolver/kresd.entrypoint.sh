#!/bin/bash

exec /var/opt/knot-resolver/.install/sbin/kresd -c /etc/knot-resolver/kresd.conf -v -f 1 /dev/shm >> /log/kresd.log
