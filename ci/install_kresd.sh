#!/usr/bin/env bash
apt-get install -y apt-transport-https -qq
wget -O /etc/apt/trusted.gpg.d/knot.gpg https://packages.sury.org/knot/apt.gpg
wget -O /etc/apt/trusted.gpg.d/knot-resolver.gpg https://packages.sury.org/knot-resolver/apt.gpg
echo "deb https://deb.knot-dns.cz/knot/ stretch main" > /etc/apt/sources.list.d/knot.list
echo "deb https://deb.knot-dns.cz/knot-resolver/ stretch main" > /etc/apt/sources.list.d/knot-resolver.list
apt-get update -qq
apt-get install -y knot-resolver -qq
