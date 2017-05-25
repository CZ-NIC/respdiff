#!/bin/bash


IP=$1
PORT=$2

PID=$(netstat -tuapn |grep $IP:$PORT | awk  '{print $(NF)}' | grep -o '[0-9]*' | head -1)
echo $PID
if [ "$PID" == "" ]; then
    #ok, that process not exist
    exit 0
fi

kill -SIGTERM $PID
if [ $? -ne 0 ]; then
    echo NOK 
    exit 1
fi

exit 0
