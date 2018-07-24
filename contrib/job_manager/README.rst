Respdiff contrib: Job Manager
=============================

Tools to manage respdiff jobs. These scripts are intended for use with
knot-resolver CI.

* ``create.py``: Creates all necessary config files for given test case and
kresd version. Docker and docker-compose is used to run the resolvers. Also
creates a ``run_respdiff.sh`` script which can be executed to run the entire
test, including build, setup and teardown.
* ``submit.py``: Submits the created job to a local HTCondor cluster.


Requirements
------------

Latest upstream versions of docker/docker-compose are recommended!

* docker-ce
* docker-compose
* pip3 install -r contrib/job_manager/requirements.txt


Example Usage
-------------

.. code-block:: console

   $ # create job directories for all 'shortlist*' test cases (default) for v2.4.0
   $ ./create.py v2.4.0
   /var/opt/respdiff/v2.4.0/shortlist.fwd-udp6-kresd.udp6.j384
   /var/opt/respdiff/v2.4.0/shortlist.fwd-udp6-unbound.tcp6.j384
   /var/opt/respdiff/v2.4.0/shortlist.fwd-tls6-kresd.udp6.j128
   /var/opt/respdiff/v2.4.0/shortlist.iter.udp6.j384
   /var/opt/respdiff/v2.4.0/shortlist.fwd-udp6-unbound.tls6.j384
   /var/opt/respdiff/v2.4.0/shortlist.iter.tls6.j384
   /var/opt/respdiff/v2.4.0/shortlist.fwd-udp6-unbound.udp6.j384

   $ # create job directory for a specific test case for commit cc036420
   $ ./create.py cc036420 -t shortlist.fwd-udp6-kresd.udp6.j384
   /var/tmp/respdiff-jobs/cc036420/shortlist.fwd-udp6-kresd.udp6.j384

.. code-block:: console

   $ # submit a prepared job to htcondor cluster to be executed once
   $ ./submit.py /var/tmp/respdiff-jobs/cc036420/shortlist.fwd-udp6-kresd.udp6.j384

   $ # submit a prepared job to htcondor cluster, execute it twice with a higher
   $ # priority and wait until all jobs are done
   $ ./submit.py -c 2 -p 10 -w /var/tmp/respdiff-jobs/cc036420/shortlist.fwd-udp6-kresd.udp6.j384

   $ # submit multiple jobs at once, execute every job twice
   $ ./submit.py -c 2 /var/opt/respdiff/v2.4.0/shortlist.iter.udp6.j384 /var/opt/respdiff/v2.4.0/shortlist.fwd-udp6-unbound.udp6.j384

.. code-block:: console

   $ # chain create.py and submit.py together to submit all 'shortlist*' test cases
   $ # for commit cc036420 to htcondor cluster
   $ ./submit.py $(./create.py cc036420)
