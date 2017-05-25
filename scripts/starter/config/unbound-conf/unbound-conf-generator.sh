#!/bin/bash

ROOT=$(readlink -e $(dirname $(readlink -e "$0")))
IP_ADDR="$1"
PORT="$2"
CLIENT="$3"

cat >$ROOT/unbound.conf <<EOL
server:
    username: kresdbench
    directory: /tmp/kresdbench/unbound-conf
    chroot: /tmp/kresdbench/unbound-conf
    pidfile: "/tmp/kresdbench/unbound-conf/unbound.pid"
    auto-trust-anchor-file: "/tmp/kresdbench/unbound-conf/root.key"

    ip-address: $IP_ADDR
    port: $PORT
    msg-cache-size: 500m
    msg-cache-slabs: 2
    neg-cache-size: 500m
    rrset-cache-size: 500m
    rrset-cache-slabs: 2
    key-cache-size: 500m
    key-cache-slabs: 2
    num-threads: 1

    access-control: $CLIENT/32 allow

remote-control:
    control-enable: no
    control-interface: $IP_ADDR    
    
    # Unbound-control key file
    control-key-file: "/tmp/kresdbench/unbound-conf/unbound_control.key"
    
    # Unbound-control cert file
    control-key-file: "/tmp/kresdbench/unbound-conf/unbound_control.pem"
    
    # Unbound server certificate file
    server-cert-file: "/tmp/kresdbench/unbound-conf/unbound_server.pem"
    
    # Unbound server key file.
    server-key-file: "/tmp/kresdbench/unbound-conf/unbound_server.key" 
EOL
echo "OK"
exit 0
