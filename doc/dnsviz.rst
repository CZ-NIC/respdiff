Dnsviz
======

Usage
-----

.. code-block:: console

  $ ./dnsviz.py domains_file  # basic example
  $ ./dnsviz.py --help        # for more info


Description
-----------

``dnsviz.py`` utilizes `DNSViz <https://github.com/dnsviz/dnsviz>`_ ``probe``
and ``grok`` commands to analyze the list of domains in a given input file.

Output is processed and errors and warning for analyzed domains is stored in
the output file, which can the be used for additional filtering in
``diffsum.py`` utility.
