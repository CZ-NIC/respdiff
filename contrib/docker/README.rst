Respdiff contrib: Docker
========================

This directory contains Dockerfiles that create images which are used
for Knot Resolver CI testing.

* ``bind/``: BIND9 compiled from git tag/branch.
* ``unbound/``: Unbound from latest ``*.tar.gz``.
* ``knot-resolver-buildenv/``: Build environment for Knot Resolver.
* ``knot-resolver-fedora/``: Experimental Knot Resolver build on Fedora.
* ``knot-resolver/``: Knot Resolver compiled from specific git sha.

These containers are also available in our
`registry <https://gitlab.labs.nic.cz/knot/respdiff/container_registry>`__.

``knot-resolver`` container
---------------------------

The ``knot-resolver`` container is not available, as it's supposed to be
re-build often, for every commmit. Only the base build environment
``knot-resolver-buildenv`` is available from the registry.

To build the container locally, with the desired git version:

.. code-block:: console

   $ export GIT_SHA=9a2bf9bfa7c3d4a9bcc83357895c5402bb3cab94
   $ docker build -t knot-resolver:$GIT_SHA --build-arg GIT_SHA=$GIT_SHA knot-resolver

**Only use commit sha or tags.** Using branch names may lead to unexpected behaviour,
as the container cache with outdated code might be used, despite any updates to the
branch itself.
