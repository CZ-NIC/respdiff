#!/bin/bash

ROOT=$(readlink -e $(dirname $(readlink -e "$0")))
IP_ADDR="$1"
PORT="$2"

cat >$ROOT/kresd.conf <<EOL
user('root','root')

-- For DNSSEC
trust_anchors.add('. IN DS 20326 8 2 E06D44B80B8F1D39A95C0B0D7C65D08458E880409BBC683457104237C7F8EC8D')
trust_anchors.add('. IN DS 19036 8 2 49AAC11D7B6F6446702E54A1607371607A1A41855200FD2CE1CDDE32F24E8FB5')

-- Settings for LMDB
cache.size = 3072*MB

-- Net config
net.listen('$IP_ADDR', $PORT)

modules = { 'workarounds < iterate' }

EOL
echo "OK"
exit 0