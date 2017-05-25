#!/bin/bash

ROOT=$(readlink -e $(dirname $(readlink -e "$0")))
IP_ADDR="$1"
PORT="$2"
CLIENT="$3"

cat >$ROOT/bind.conf <<EOL
acl resperf {
	$CLIENT/32;
	localhost;
	localnets;
};

managed-keys {
	# DNSKEY for the root zone.     
	# Updates are published on root-dnssec-announce@icann.org     
	. initial-key 257 3 8 "AwEAAagAIKlVZrpC6Ia7gEzahOR+9W29euxhJhVVLOyQbSEW0O8gcCjF FVQUTf6v58fLjwBd0YI0EzrAcQqBGCzh/RStIoO8g0NfnfL2MTJRkxoX bfDaUeVPQuYEhg37NZWAJQ9VnMVDxP/VHL496M/QZxkjf5/Efucp2gaD X6RS6CXpoY68LsvPVjR0ZSwzz1apAzvN9dlzEheX7ICJBBtuA6G3LQpz W5hOA2hzCTMjJPJ8LbqF6dsV6DoBQzgul0sGIcGOYl7OyQdXfZ57relS Qageu+ipAdTTJ25AsRTAoub8ONGcLmqrAmRLKBP1dfwhYB4N7knNnulq QxA+Uk1ihz0=";
};

options {
	directory "/tmp/kresdbench/bind-conf";

	dnssec-enable yes;
	dnssec-validation yes;

	auth-nxdomain no;    # conform to RFC1035
	
	recursion yes;
	
	//allow these ips
	allow-query { resperf; };

	//allow querry from cache for these hosts
	allow-query-cache{ resperf; };

	acache-enable yes;
	max-acache-size 900M;

	max-cache-size 900M;

	statistics-file "/tmp/kresdbench/bind/named.stats";
	dump-file "/tmp/kresdbench/bind/cache_dump.db";
	listen-on port $PORT { $IP_ADDR; };
};

key "rndc-key" {
	algorithm hmac-md5;
	secret "vOk2FsSix7hSXBJZvigQuw==";
};

controls {
	inet * port 953
		allow { $CLIENT; } keys { "rndc-key"; };
};
EOL
echo "OK"
exit 0
