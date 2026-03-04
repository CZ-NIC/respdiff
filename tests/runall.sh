#!/usr/bin/bash
set -o nounset -o errexit -o xtrace

ENVDIR="test-envdir"
QLIST="test-qlist"

rm -vrf "$ENVDIR"

cat >"$QLIST" <<EOF
www.google.com A
. DS
www.facebook.com AAAA
1.10.in-addr.arpa. NS
arpa. NS
. NS
nonexistent.arpa. HINFO
EOF
./qprep.py "$ENVDIR" <"$QLIST"
./orchestrator.py "$ENVDIR"
./msgdiff.py "$ENVDIR"
./diffsum.py "$ENVDIR"
./diffrepro.py "$ENVDIR"
./diffsum.py "$ENVDIR"
./histogram.py "$ENVDIR"
