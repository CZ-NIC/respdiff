Msgdiff
=======

Usage
-----

.. code-block:: console

   $ ./msgdiff.py "${DIR}"    # basic example
   $ ./msgdiff.py --help      # for more info


Description
-----------

Gathered answers can be compared using the ``msgdiff.py`` tool.
which reads configuration from config file section ``[diff]``.

The tool refers to one server as ``target`` (configured in ``[diff]``
section) and to remaining servers as ``others``. Msgdiff compares specified
``criteria`` and stores results in the LMDB and the JSON datafile.

The created JSON datafile contains the information about the mismatches. This
datafile is necessary for other tools in the respdiff toolchain. The format of
this file is subject to change and backwards compatibility is not guaranteed.


Notes
-----

- Performance of ``msgdiff.py`` can be slightly boosted by compiling
  ``dnspython`` with CPython.
- If you change the ``criteria``, you can re-run ``msgdiff.py`` and the rest of
  the toolchain on the same LMDB without gathering the answers again.
