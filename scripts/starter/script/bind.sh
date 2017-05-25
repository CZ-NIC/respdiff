#!/bin/bash

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games"

ROOT=$(readlink -e $(dirname $(readlink -e "$0")))
BIND9_DIR="$ROOT/bind9"
LOG="$ROOT/logfile.log"
REPO="https://source.isc.org/git/bind9.git"
CONFIG="$ROOT/bind-conf/bind.conf"
BIN_FOLDER="$BIND9_DIR/bin/named"

#################################################
### Update Bind
### installed to /usr/local
#################################################
cd $ROOT
git clone $REPO &>>$LOG
cd $BIND9_DIR 

RETVAL="$(git pull)"

sudo make clean &>>$LOG

./configure &>>$LOG
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

# Start bind
cd $BIN_FOLDER

#without sudo does not start rndc port
sudo ./named -u bind -n 1 -c $CONFIG &>>$LOG 

echo "OK"
exit 0
