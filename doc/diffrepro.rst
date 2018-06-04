Diffrepro
=========

Usage
-----

.. code-block:: console

   $ ./diffrepro.py "${DIR}"    # basic example
   $ ./diffrepro.py --help      # for more info


Description
-----------

Use of this tool is optional. It can be used to filter differences that either have and *unstable upstream* or are *not reproducible* (for explanation, see ``diffrepro.py`` documentation).

The tool can run queries in parallel (like orchestrator), or sequentially (slower,
but more predictable).

If it's used to test local resolvers, they should be restarted (and cache cleared) between
the queries. This can be achieved by providing a path to restart script in
``restart_script`` key in each server's section in the config file. This script
will be executed after each batch (parallel mode) or query (sequential mode)
for every server.

The output is written to the JSON report and other tools automatically use this
data if present.


Notes
-----

* If you want to ensure the most reliable reproducibility use ``-s`` argument
  to force sequential, one by one, processing of the differences. With scripts
  than ensure resolver restart (and clean up of the cache), this can find the
  differences that can be reproduced in the most reliable way. Beware this
  option can be very slow for large number of differneces.
