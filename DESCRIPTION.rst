runtests
========

Runtests is a test harness and runner, originally written for JS interpreter
testing.

Runs all the files you specify through an interpreter you specify, and collates
the exit codes and output.

Tests may be run sequentially, or in parallel using the HTCondor_ framework.
Results are collated in a file dump of some sort, or in a database for easy
querying.

.. _HTCondor: https://research.cs.wisc.edu/htcondor/
