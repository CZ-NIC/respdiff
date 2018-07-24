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

Latest upstream version of docker/docker-compose are recommended!

* docker-ce
* docker-compose
* pip3 install -r contrib/job_manager/requirements.txt
