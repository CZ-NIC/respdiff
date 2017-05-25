#!/bin/bash

ROOT=$(readlink -e $(dirname $(readlink -e "$0")))
KRESD_DIR="$ROOT/knot-resolver"
LOG="$ROOT/logfile.log"
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games"
REPO="https://github.com/CZ-NIC/knot-resolver.git"
CONFIG="$ROOT/knot-conf/kresd.conf"
BRANCH="${1:-master}"

#################################################
### Update Knot Resolver
#################################################
cd $ROOT
git clone $REPO &>>$LOG
cd $KRESD_DIR
git fetch &>>$LOG
git pull &>>/dev/null
git checkout "$BRANCH" &>>$LOG
if [ $? -eq 1 ]; then
    echo "Wrong branch name."
    exit 1
fi
RETVAL=$(git describe "$BRANCH")
git pull &>>/dev/null

make clean &>>$LOG
if [ $? -ne 0 ]; then
    echo NOK &>>$LOG
    exit 1
fi

sudo make PREFIX="/usr/local" &>>$LOG
if [ $? -ne 0 ]; then
    echo NOK &>>$LOG 
    exit 1
fi

sudo make install PREFIX="/usr/local" &>>$LOG
if [ $? -ne 0 ]; then
    echo NOK &>>$LOG
    exit 1
fi

#service kresd start
sudo daemon -- /usr/local/sbin/kresd --config $CONFIG -f 1 /run/knot-resolver/cache
sleep 1

#create new socat for command communication
sudo daemon -- socat tcp-listen:50004,fork unix:/run/knot-resolver/cache/tty/`sudo ls /run/knot-resolver/cache/tty/ | head -1`
echo $RETVAL
exit 0
