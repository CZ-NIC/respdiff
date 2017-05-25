#!/bin/bash

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games"

ROOT=$(readlink -e $(dirname $(readlink -e "$0")))
PDNS_DIR="$ROOT/pdns/pdns/recursordist"
LOG="$ROOT/logfile.log"
REPO="https://github.com/PowerDNS/pdns.git"
CONFIG="$ROOT/pdns-conf/pdns.conf"

#################################################
### Update PowerDns
### Config file: /usr/local/etc/recursor.conf
### Installed to /home/jholusa/resolvers/pdns/
###     pdns/recursordist/pdns_recursor
#################################################

cd $ROOT
git clone $REPO
cd $PDNS_DIR

RETVAL="$(git pull)"

make clean || true

sudo ./bootstrap &>>$LOG
if [ $? -ne 0 ]; then
    echo NOK &>>$LOG
    exit 1
fi

sudo ./configure &>>$LOG
if [ $? -ne 0 ]; then
    echo NOK &>>$LOG
    exit 1
fi

sudo make &>>$LOG
if [ $? -ne 0 ]; then
    echo NOK &>>$LOG
    exit 1
fi

cd $PDNS_DIR
sudo ./pdns_recursor --config-dir="/tmp/kresdbench/pdns-conf"

echo "OK"
exit 0
