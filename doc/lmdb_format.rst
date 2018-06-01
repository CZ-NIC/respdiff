LMDB Binary Format
==================

If the data was gathered using tools other than ``orchestartor.py``, e.g.
`dnsjit <https://github.com/DNS-OARC/dnsjit>`__, the following LMDB database
environment can be used to achieve compatibility with the rest of respdiff
toolchain.

All numbers represented in binary format defined below use the **little endian** byte order.

Database ``queries``
--------------------

``queries`` database is used to store the wire format of queries that were sent
to the servers. Each query has a unique integer identifier, ``<QID>``.

+-----------+-----------------+-----------------------------+------------------+
| Key       | Key Type        | Value Description           | Value Type       |
+===========+=================+=============================+==================+
| ``<QID>`` | 4B unsigned int | DNS query sent to server(s) | DNS wire format  |
+-----------+-----------------+-----------------------------+------------------+

Database ``answers``
--------------------

``answers`` database stores the binary responses from the queried servers.

If there are multiple servers, their responses are stored within a single
``<QID>`` key.  Multiple responses are stored within the value by simply
concatenating them in the binary format of ``response`` described below.  Please
note the order of responses is significant and must correspond with the server
definition in the ``meta`` database.

+-----------+-----------------+--------------------------------+---------------------------------------+
| Key       | Key Type        | Value Description              | Value Type                            |
+===========+=================+================================+=======================================+
| ``<QID>`` | 4B unsigned int | DNS response(s) from server(s) | One or more ``response`` (see below)  |
+-----------+-----------------+--------------------------------+---------------------------------------+

``response``
~~~~~~~~~~~~

``response`` represents a single DNS response from a server and has the
following binary format::

     . 0    1    2    3    4    5    6      ...
     +----+----+----+----+----+----+----\\----+
     |        time       | length  |   wire   |
     +----+----+----+----+----+----+----\\----+

+------------+--------------------------+---------------------------------------------------------------------------------------------------------------------------+
| Label      | Type                     | Description                                                                                                               |
+============+==========================+===========================================================================================================================+
| ``time``   | 4B unsigned int          | time to receive the answer in microseconds; ``4294967295`` (``FF FF FF FF``) means *timeout*                              |
+------------+--------------------------+---------------------------------------------------------------------------------------------------------------------------+
| ``length`` | 2B unsigned int          | byte-length of the DNS ``wire`` format message that may follow; (``length`` is always present, even in case of *timeout*) |
+------------+--------------------------+---------------------------------------------------------------------------------------------------------------------------+
| ``wire``   | ``length`` B binary blob | DNS wire format of the message received from server (``wire`` is present only if ``length`` isn't zero)                   |
+------------+--------------------------+---------------------------------------------------------------------------------------------------------------------------+

Database ``meta``
-----------------

``meta`` database stores additional information used for further processing of the data.

+----------------+----------+-------------------------------------------------------------------+------------------+
| Key            | Key Type | Value Description                                                 | Value Type       |
+================+==========+===================================================================+==================+
| ``version``    | ASCII    | respdiff binary format version (current: ``2018-05-21``)          | ASCII            |
+----------------+----------+-------------------------------------------------------------------+------------------+
| ``servers``    | ASCII    | number of servers responses are collected from                    | 4B unsigned int  |
+----------------+----------+-------------------------------------------------------------------+------------------+
| ``name0``      | ASCII    | name identifier of the first server (same as in ``respdiff.cfg``) | ASCII            |
+----------------+----------+-------------------------------------------------------------------+------------------+
| ``name1``      | ASCII    | name identifier of the second server                              | ASCII            |
+----------------+----------+-------------------------------------------------------------------+------------------+
| ``name<N>``    | ASCII    | name identifier of the ``N+1``-th server                          | ASCII            |
+----------------+----------+-------------------------------------------------------------------+------------------+
| ``start_time`` | ASCII    | (*optional*) unix timestamp of the start of data collection       | 4B unsigned int  |
+----------------+----------+-------------------------------------------------------------------+------------------+
| ``end_time``   | ASCII    | (*optional*) unix timestamp of the end of data collection         | 4B unsigned int  |
+----------------+----------+-------------------------------------------------------------------+------------------+
