#!/usr/bin/bash
set -o nounset -o errexit -o xtrace

ENVDIR="test-envdir"
QLIST="test-qlist"

rm -vrf "$ENVDIR"

cat >"$QLIST" <<EOF
www.google.com A 1
. DS 1
www.facebook.com AAAA 1
1.10.in-addr.arpa. NS 4
arpa. NS 1
. NS 1
nonexistent.arpa. HINFO 1
EOF
./qprep.py -f text-with-weights "$ENVDIR" <"$QLIST"
./orchestrator.py "$ENVDIR"
./msgdiff.py "$ENVDIR"
./diffsum.py "$ENVDIR"
./diffrepro.py "$ENVDIR"
./diffsum.py "$ENVDIR"
./histogram.py "$ENVDIR"
