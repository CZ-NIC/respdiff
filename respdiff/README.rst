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
4. diffsum: summarize differences into textual report

This split allows us to repeat steps using the same data as necessary,
e.g. run analysis with different parameters without re-querying the
resolvers.

All tools take a folder with LMDB environment as an argument.
Also optional argument is a configuration file (example: see ``respdiff.cfg``).


Qprep
-----
Tool ``qprep.py`` reads list of queries in text format ``<name> <RR type>`` from standard input
and generates wire format for the queries. The wire format is stored in LMDB.

Right now it hardcodes EDNS buffer size 4096 B and DO flag set.
Future versions might allow some query customization.


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
in the LMDB.


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


Usage
-----
Please note that this is very basic use-case where nothing is prepared beforehand.

::

  $ ./qprep.py "${DIR}" < list_of_queries_in_text_format
  $ ./orchestrator.py "${DIR}"  # send queries and gather answers
  $ ./msgdiff.py "${DIR}"       # compute diffs
  $ ./diffsum.py "${DIR}" > "${DIR}"/"${DIR}".txt  # generate text report

It is possible to re-use results of ``qprep``,
just copy the directory somewhere and run ``orchestrator`` again.
Also, you can re-run ``msgdiff`` and ``diffsum`` using different configuration.
