Diffsum
=======

Usage
-----

.. code-block:: console

   $ ./diffsum.py "${DIR}"    # basic example
   $ ./diffsum.py --help      # for more info


Description
-----------

Differences computed by ``msgdiff.py`` can be translated into text report using
tool ``diffsum.py`` which computes summary based on that comparison's results.

The report uses the following terms:

- *upstream unstable* represents queries, where the servers other than
  ``target`` haven't received the same answer, thus the source (upstream) of
  these queries is considered unstable. These queries aren't counted further
  towards the other statistics.
- *not reproducible* appears in cases where ``diffrepro.py`` tool was used
  to attempt to reproduce the measured differences. In case the difference
  doesn't match exactly the one before, the query is ignored in further
  processing.
- *target disagreements* refers to cases, when there's a difference
  between the answer from ``target`` server and the others server, and the
  other servers agree on the answer (there is no difference between them).
  These are the most interesting cases that are analysed further.
- *manually ignored* is the number of queries which were ommitted from the
  report by using `--without-ref-failing` or `--without-ref-unstable` along
  with a reference statistics file

The summary evaluates how many *target disagreements* there were in particular
*fields* (or ``criteria``), and what did these mismatches look like. It produces
both textual output and machine readable file (``*.json``).


Notes
-----

* If you adjust the ``field_weights``, just re-order the fields. Don't remove
  them, otherwise there'll be issues if such field is ever encountered when
  producing the summary.
* In case you update respdiff and ``diffsum.py`` doesn't work, check the
  changelog. If a new field was added, adjust your config accordingly.
* Redirect *stdout* of the command to a text file in case you want to keep the
  textual report for future reference.
* If you want a comprehensive list of mismatched queries in the text report,
  use ``-l 0`` argument.
