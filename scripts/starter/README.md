# Starter Script
Script helps you to start resolver on the remote server you have access.

## Parameters
* `-h` - Print help message simmilar to this one. 
* `-i <ip>` - set ip of the remote server.
* `-p <port>` - set port at which should resolver run at the remote server.
* `-u <userid>` - set the user name, which has account at the remote server and has valid public key at that server.
* `-k` - If this flag set, it means that you are going to kill server, not start.
* `-r <resolver>` - What resolver do you want to start. Possible values are knot, bind, unbound and pdns.
* `-l <local_port_name>` - local port name from which you are going to send requests to the remote server. You can get this name by using command `ifconfig` or `ipconfig`(windows users).


## Examples of use
* To start a bind resolver at ip 172.20.20.160 and port 50001 using local port eth0 - `python2.7 start -i 172.20.20.160 -p 50001 -u jholusa -r bind -l eth0`
* To stop bind resolver with above ip a port `python2.7 start -i 172.20.20.160 -p 50001 -u jholusa -k`

## Output
Script creates logfile `logfile.log` with some usefull information for debugging.

# Known problems
* There is some problem with starting pdns resolver remotely. It seems that `./configure` cannot be run in `pdns.sh` script.