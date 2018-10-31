Dnsviz
======

Requirements
------------

This tool requires ``dnsviz`` command to be installed. Use you distribution packages
or install it using pip. Note that dnsviz dependencies have to be installed separately.

Fedora
~~~~~~

The following installs dnsviz for Python3 from git (with latest Python 3 fixes).

.. code-block:: console

   $ dnf install openssl-devel python3-devel swig gcc redhat-rpm-config git
   $ pip3 install git+https://github.com/dnsviz/dnsviz.git M2Crypto dnspython

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
