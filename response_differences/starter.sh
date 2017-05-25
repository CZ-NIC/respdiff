#!/bin/bash

PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/usr/games:/usr/local/games"
LOG="stdout.log"
BASEDIR=$(dirname "$0") 

# ssh setup
eval `ssh-agent -s`
ssh-add /home/kresdbench/.ssh/id_benchmark
ssh-add /home/kresdbench/.ssh/gitlab_kresdbench

#check git repository
git -C $BASEDIR pull

#run the python benchar
python2.7 $BASEDIR/respdif -c $BASEDIR/config/kresdtest.cfg -i $BASEDIR/data/q_no_mcafee --json &>>$BASEDIR/$LOG

#remove ssh key
ssh-add -d /home/kresdbench/.ssh/id_benchmark
ssh-add -d /home/kresdbench/.ssh/gitlab_kresdbench
