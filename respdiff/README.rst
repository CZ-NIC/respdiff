==========================
Respdiff second generation
==========================

Respdiff is an abbreviation from "response differences" used as name for set of tools
allowing to gather answers to DNS queries from DNS servers and compare them based on specified criteria.


Overview
--------
Respdiff v2 is conceptually chain of independent tools:

1. qprep: generate queries in wire format
2. orchestrator: send pre-generated wire format to servers and gather answers
3. msgdiff: compare DNS answers
4. diffrepro: (optional) attempt to reproduce the differences
4. diffsum: summarize differences into textual report
5. histogram: plot graph of answer latencies

This split allows us to repeat steps using the same data as necessary,
e.g. run analysis with different parameters without re-querying the
resolvers.

All tools take a folder with LMDB environment as an argument.
Also optional argument is a configuration file (example: see ``respdiff.cfg``).


Qprep
-----
Tool ``qprep.py`` reads list of queries and stores wire format in a new LMDB
environment specified on command line.
Two input formats are accepted: text and PCAP.

Text format is list of queries in form ``<name> <RR type>`` and is read
from standard input, one query on one input line.
When generating wire format from text, the tool hardcodes EDNS buffer size
4096 B and DO flag set. Future versions might allow some query customization.

Second accepted format is PCAP file. The tool copies wire format from Ethernet
frames containing IP v4/v6 packets with UDP/TCP transport layer on port 53
if QR bit in DNS header is not set. Packets on port 53 which cannot be parsed
as DNS packets are copied verbatim into the database.


Orchestrator
------------
Tool ``orchestrator.py`` then reads query wire format from LMDB, sends it to
DNS servers and stores answer from each server inside LMDB.

Names of servers are specified in config file section ``[servers]`` in key ``names``.
IP address and port of each server is read from the config file.

Multiple queries might be send in parallel,
see ``[sendrecv]`` section in the config file.


Msgdiff
-------
Gathered answers can be analyzed using tool ``msgdiff.py``
which reads configuration from config file section ``[diff]``.

The tool refers to one resolver as ``target`` and to remaining servers
as ``others``. Msgdiff compares specified fields and stores result
in the LMDB and the JSON datafile.


Diffrepro
---------

Use of this tool is optional. It can be used to filter "unstable" differences,
which aren't reproducible. If the upstream answers differ (between resolvers or
over time), the query is flagged as unstable.

The tool can run queries in parallel (like orchestrator), or sequentially (slower,
but more predictable). Resolvers should be restarted (and cache cleared) between
the queries. Path to an executable restart script can be provided with
``restart_script`` value in each resolver's section in config.

The output is written to the JSON datafile and other tools automatically use
this data if present.


Diffsum
-------
Diffs computed by ``msgdiff.py`` can be translated into text report
using tool ``diffsum.py`` which computes statistics based on that comparion results.

Answers where ``others`` do not agree with each other are simply counted but
not processed further.

Answers where ``others`` agree but the ``target``
returned a different answer than all ``others`` are counted separately
with higher granularity, producing stats for each field in DNS message
(rcode, flags, answer section, ...).

Ordering and grouping of mismatches is specified in ``[report]`` section of config file.


Histogram
---------

``orchestrator.py`` saves the latency for each answer in LMDB. Afterwards, they
can be used to analyze the performance of the resolver. ``histrogram.py`` generates a
`logarithmic percentile histogram <https://blog.powerdns.com/2017/11/02/dns-performance-metrics-the-logarithmic-percentile-histogram/>`_
from these latencies.


Usage
-----
Please note that this is very basic use-case where nothing is prepared beforehand.

First, run ``qprep.py`` to prepare the queries.

.. code-block:: console

   $ ./qprep.py "${DIR}" < list_of_queries_in_text_format

These results can be re-used by copying the directory somewhere and executing
``orchestrator.py`` again.

Next, configure ``servers`` in ``respdiff.cfg`` and run ``orchestrator.py`` to
send and gather queries.

.. code-block:: console

  $ ./orchestrator.py "${DIR}"

Compute differences in responses and generate a text report from them.

.. code-block:: console

  $ ./msgdiff.py "${DIR}"
  $ ./diffsum.py "${DIR}" > "${DIR}"/"${DIR}".txt

Plot a logarithmic percentile graph of answer latencies.

.. code-block:: console

  $ ./histogram.py -o histogram.svg "${DIR}"

You can also re-run ``msgdiff.py`` and ``diffsum.py`` using different configuration.
