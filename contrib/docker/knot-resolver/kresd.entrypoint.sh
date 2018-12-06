#!/bin/bash

exec /var/opt/knot-resolver/.install/sbin/kresd -c /etc/knot-resolver/kresd.conf -K /etc/knot-resolver/root.keys -v -f 1 /dev/shm &>> /log/kresd.log
