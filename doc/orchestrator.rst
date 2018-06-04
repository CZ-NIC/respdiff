Orchestrator
============

Usage
-----

.. code-block:: console

  $ ./orchestrator.py "${DIR}"    # basic example
  $ ./orchestrator.py --help      # for more info


Description
-----------

``orchestrator.py`` reads query wire format from LMDB and sends it to
configured DNS servers and stores the received answer from each server inside LMDB.

Names of servers are specified in ``names`` key in ``[servers]`` section of the
config file.  IP address, port and protocol used for each server is also read
from the config file (see ``respdiff.cfg`` for example).

Multiple queries might be sent in parallel, see ``jobs`` option in
``[sendrecv]`` section of the config file.

By default, each job (process/thread) sends another query as soon as the answer
to the previous one is received and processed. It is possible to add a random
or fixed delay between sending the queries by customizing the
``time_delay_min`` and ``time_delay_max`` options in ``[sendrecv]`` section of
the config file.

The tool automatically aborts in case it receives ``max_timeouts`` of
consecutive timeouts from a single server. To supress this behaviour, use
``--ignore-timeout`` argument.
