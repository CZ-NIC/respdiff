#!/usr/bin/env bash
set -o errexit -o nounset -o xtrace
time wget https://gitlab.nic.cz/knot/respdiff/snippets/238/raw?inline=false -O - | head -n 1000 > /tmp/queries.txt
CONFIG="respdiff.cfg"

rm -r /tmp/respdiff.db ||:

./qprep.py /tmp/respdiff.db < /tmp/queries.txt
time ./orchestrator.py /tmp/respdiff.db -c "${CONFIG}"
time ./msgdiff.py /tmp/respdiff.db -c "${CONFIG}"
./diffrepro.py /tmp/respdiff.db -c "${CONFIG}"
./diffsum.py /tmp/respdiff.db -c "${CONFIG}"
./sumstat.py /tmp/respdiff.db/report.json
./statcmp.py /tmp/respdiff.db/report.json -l test

# it must not explode/raise an unhandled exception
