#!/usr/bin/env bash
set -o errexit
service unbound start && service unbound status
service bind9 start && service bind9 status
cp "$(pwd)/ci/respdiff/kresd.cfg" /etc/knot-resolver/kresd.conf
service kresd start && service kresd status

wget https://gitlab.labs.nic.cz/knot/knot-resolver/snippets/69/raw?inline=false -O /tmp/queries.txt
mkdir /tmp/respdiff
tail -n 100 /tmp/queries.txt | python3 "$(pwd)/response_differences/respdiff/qprep.py" /tmp/respdiff
python3 "$(pwd)/response_differences/respdiff/orchestrator.py" /tmp/respdiff -c "$(pwd)/ci/respdiff/respdiff.cfg"
python3 "$(pwd)/response_differences/respdiff/msgdiff.py" /tmp/respdiff -c "$(pwd)/ci/respdiff/respdiff.cfg"
python3 "$(pwd)/response_differences/respdiff/diffsum.py" /tmp/respdiff -c "$(pwd)/ci/respdiff/respdiff.cfg"
