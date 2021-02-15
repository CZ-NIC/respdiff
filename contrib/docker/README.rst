Respdiff contrib: Docker
========================

This directory contains Dockerfiles that create images which are used
for Knot Resolver CI testing.

* ``bind/``: BIND9 compiled from git tag/branch.
* ``unbound/``: Unbound from latest ``*.tar.gz``.
* ``powerdns/``: PowerDNS compiled from git tag/branch.
* ``knot-resolver-buildenv/``: Build environment for Knot Resolver.
* ``knot-resolver-fedora/``: Experimental Knot Resolver build on Fedora.
* ``knot-resolver/``: Knot Resolver compiled from specific git sha.

These containers are also available in our
`registry <https://gitlab.nic.cz/knot/respdiff/container_registry>`__.

``knot-resolver`` container
---------------------------

The ``knot-resolver`` container is not available from the registry, as it's
supposed to be re-build often, for every commit. Only the base build
environment ``knot-resolver-buildenv`` is available from the registry.

To build the container locally, with the desired git version:

.. code-block:: console

   $ export GIT_SHA=9a2bf9bfa7c3d4a9bcc83357895c5402bb3cab94
   $ docker build -t knot-resolver:$GIT_SHA --build-arg GIT_SHA=$GIT_SHA knot-resolver

**Only use commit sha or tags.** Using branch names may lead to unexpected behaviour,
as the container cache with outdated code might be used, despite any updates to the
branch itself.

For compiling with different Knot DNS versions, use ``--build_arg KNOT_BRANCH=x.y``.

Registry Maintance - new builds
-------------------------------

.. code-block:: console

   # knot-resolver-buildenv container build
   $ export KNOT_BRANCH=3.0
   $ docker build --no-cache -t registry.nic.cz/knot/respdiff/knot-resolver-buildenv:knot-$KNOT_BRANCH --build-arg KNOT_BRANCH=$KNOT_BRANCH knot-resolver-buildenv

   # bind container build
   $ export GIT_TAG=v9_16_6
   $ docker build --no-cache -t registry.nic.cz/knot/respdiff/bind:$GIT_TAG --build-arg GIT_TAG=$GIT_TAG bind

   # unbound container build
   $ export GIT_TAG=release-1.13.0
   $ docker build --no-cache -t registry.nic.cz/knot/respdiff/unbound:$GIT_TAG --build-arg GIT_TAG=$GIT_TAG unbound

   # powerdns container build
   $ export GIT_TAG=rec-4.3.4
   $ docker build --no-cache -t registry.nic.cz/knot/respdiff/powerdns:$GIT_TAG --build-arg GIT_TAG=$GIT_TAG powerdns

   # dnsdist container build
   $ export GIT_TAG=dnsdist-1.5.0
   $ docker build --no-cache -t registry.nic.cz/knot/respdiff/dnsdist:$GIT_TAG --build-arg GIT_TAG=$GIT_TAG dnsdist

   # dnsperf container build
   $ export GIT_TAG=v2.4.1
   $ docker build --no-cache -t registry.nic.cz/knot/respdiff/dnsperf:$GIT_TAG --build-arg GIT_TAG=$GIT_TAG dnsperf

   # push containers to registry
   $ docker login registry.nic.cz
   $ docker push registry.nic.cz/knot/respdiff/knot-resolver-buildenv:knot-$KNOT_BRANCH
   $ docker push registry.nic.cz/knot/respdiff/bind:$GIT_TAG
   $ docker push registry.nic.cz/knot/respdiff/unbound:$GIT_TAG
   $ docker push registry.nic.cz/knot/respdiff/powerdns:$GIT_TAG
   $ docker push registry.nic.cz/knot/respdiff/dnsdist:$GIT_TAG
   $ docker push registry.nic.cz/knot/respdiff/dnsperf:$GIT_TAG
