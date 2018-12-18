QExport
=======

Usage
-----

.. code-block:: console

  $ ./qexport.py --envdir "${DIR}" report.json --failing  # basic example
  $ ./qexport.py --help                                   # for more info


Description
-----------

``qexport.py`` reads given report(s) and print out failing / unstable (or both)
queries. One query per line is printed. The format can be either QID or other
textual query representation (these also need the LMDB database, which can be
provided with `'--envdir``). When textual representation is selected, only
unique occurences are printed (one textual representation can cover multiple
QIDs).

One of the uses of this tool is to get a list of domain for further analysis,
for example with DNSViz (or our ``dnsviz.py`` tool).
