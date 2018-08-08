Respdiff
========

Respdiff is an abbreviation from "response differences" used as name for set of
tools allowing to gather answers to DNS queries from DNS servers and compare
them based on specified criteria.

Installation
------------

.. code-block:: console

   $ git clone https://gitlab.labs.nic.cz/knot/respdiff.git
   $ cd respdiff
   $ pip3 install -r requirements.txt

Respdiff toolchain requires **Python 3.5.2+**. There are also some Python package
dependencies that are listed in ``requirements.txt``. If you'd prefer to use
your distribution packages, please install them manually instead of using
``pip3``.

Usage
-----

Please note that this is very basic use-case where nothing is prepared beforehand.

.. code-block:: console

   $ ./qprep.py "${DIR}" < list_of_queries_in_text_format
   $ ./orchestrator.py "${DIR}"
   $ ./msgdiff.py "${DIR}"
   $ ./diffsum.py "${DIR}" > "${DIR}"/"${DIR}".txt

You can also re-run ``msgdiff.py`` and ``diffsum.py`` using different configuration.

Advanced usage
~~~~~~~~~~~~~~

- Customize ``respdiff.cfg`` (see instructions in the file).
- All executable scripts in the project's repository are tools for with a
  specific purpose. You can find their documentation in `doc/ <doc/>`__ and ``--help``.
- Queries and answeres can be gathered with a different tool
  (e.g. `dnsjit <https://github.com/DNS-OARC/dnsjit>`__) and read from LMDB
  (see `doc/lmdb_format.rst <doc/lmdb_format.rst>`__ for description of the used binary format.

Overview
--------

Respdiff is conceptually chain of independent tools:

1. `qprep <doc/qprep.rst>`__: generate queries in wire format and store to LMDB
2. `orchestrator <doc/orchestrator.rst>`__: send pre-generated wire format to
   servers and gather answers to LMDB
3. `msgdiff <doc/msgdiff.rst>`__: compare DNS answers
4. `diffrepro <doc/diffrepro.rst>`__: attempt to reproduce the differences
5. `diffsum <doc/diffsum.rst>`__: summarize differences into textual and
   machine readable report
6. `histogram <doc/histogram.rst>`__: plot graph of answer latencies
7. `sumcmp <doc/sumcmp.rst>`__: compare a new diffsum report to a reference one
8. `sumstat <doc/sumstat.rst>`__: generate statistics from multiple diffsum reports
9. `statcmp <doc/statcmp.rst>`__: plot and compare statistics and reports


Changelog
---------

- 2018-06-01: reorganized tools and created a new git repo with cleaned-up history
