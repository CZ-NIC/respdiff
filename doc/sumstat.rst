Sumstat
=======

Usage
-----

.. code-block:: console

   $ ./sumstat.py $(find datadir/ -name report.json)  # basic example
   $ ./sumstat.py --help                              # for more info


Description
-----------

Generates statistics ``stats.json`` from multiple diffsum reports (``report.json``).
These stats can be used in ``statcmp.py`` to evaluate a new diffsum report to see if the
new results fall within set statistical limits.
