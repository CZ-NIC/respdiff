Respdiff contrib: Job Manager
=============================

Tools to manage respdiff jobs. These scripts are intended for use with
knot-resolver CI.

* ``create.py``: Creates all necessary config files for given test case and
kresd version. Docker and docker compose is used to run the resolvers. Also
creates a ``run_respdiff.sh`` script which can be executed to run the entire
test, including build, setup and teardown.
* ``submit.py``: Submits the created job to a local HTCondor cluster.


Requirements
------------

Latest upstream versions of docker/docker compose (v2) are recommended!

* docker-ce
* docker-compose-plugin
* pip3 install -r contrib/job_manager/requirements.txt


Example Usage
-------------

.. code-block:: console

   Create job directories for all 'shortlist*' test cases (default) for v2.4.0
   $ ./create.py v2.4.0
   /var/tmp/respdiff/v2.4.0/shortlist.fwd-udp6-kresd.udp6.j384
   /var/tmp/respdiff/v2.4.0/shortlist.fwd-udp6-unbound.tcp6.j384
   /var/tmp/respdiff/v2.4.0/shortlist.fwd-tls6-kresd.udp6.j128
   /var/tmp/respdiff/v2.4.0/shortlist.iter.udp6.j384
   /var/tmp/respdiff/v2.4.0/shortlist.fwd-udp6-unbound.tls6.j384
   /var/tmp/respdiff/v2.4.0/shortlist.iter.tls6.j384
   /var/tmp/respdiff/v2.4.0/shortlist.fwd-udp6-unbound.udp6.j384

   Create job directory for a specific test case for commit cc036420
   $ ./create.py cc036420 -t shortlist.fwd-udp6-kresd.udp6.j384
   /var/tmp/respdiff-jobs/cc036420/shortlist.fwd-udp6-kresd.udp6.j384

.. code-block:: console

   Submit a prepared job to htcondor cluster to be executed once
   $ ./submit.py /var/tmp/respdiff-jobs/cc036420/shortlist.fwd-udp6-kresd.udp6.j384

   Submit a prepared job to htcondor cluster, execute it twice with a higher
   $ # priority and wait until all jobs are done
   $ ./submit.py -c 2 -p 10 -w /var/tmp/respdiff-jobs/cc036420/shortlist.fwd-udp6-kresd.udp6.j384

   Submit multiple jobs at once, execute every job twice
   $ ./submit.py -c 2 /var/tmp/respdiff/v2.4.0/shortlist.iter.udp6.j384 /var/tmp/respdiff/v2.4.0/shortlist.fwd-udp6-unbound.udp6.j384

.. code-block:: console

   Chain create.py and submit.py together to submit all 'shortlist*' test cases
   for commit cc036420 to htcondor cluster
   $ ./submit.py $(./create.py cc036420)
