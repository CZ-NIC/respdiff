#!/bin/bash

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games"

ROOT=$(readlink -e $(dirname $(readlink -e "$0")))
UNBOUND_DIR="$ROOT/trunk"
LOG="$ROOT/logfile.log"
REPO="http://unbound.nlnetlabs.nl/svn/trunk"
CONFIG="$ROOT/unbound-conf/unbound.conf"

#################################################
### Update Unbound
#################################################

cd $ROOT
svn checkout $REPO
cd $UNBOUND_DIR

svn update &>>$LOG

sudo make clean || true

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

sudo make install &>>$LOG
if [ $? -ne 0 ]; then
    echo NOK &>>$LOG
    exit 1
fi


#service unbound start
sudo ./unbound -c $CONFIG

echo "OK"
exit 0
