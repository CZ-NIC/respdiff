#!/usr/bin/env bash
set -o errexit -o nounset -o xtrace
mkdir /tmp/respdiff.db
time wget https://gitlab.labs.nic.cz/knot/knot-resolver/snippets/69/raw?inline=false -O - | head -n 100 > /tmp/queries.txt
CONFIG="response_differences/respdiff/respdiff.cfg"

response_differences/respdiff/qprep.py /tmp/respdiff.db < /tmp/queries.txt
time response_differences/respdiff/orchestrator.py /tmp/respdiff.db -c "${CONFIG}"
time response_differences/respdiff/msgdiff.py /tmp/respdiff.db -c "${CONFIG}"
response_differences/respdiff/diffsum.py /tmp/respdiff.db -c "${CONFIG}"

# it must not explode/raise an unhandled exception
