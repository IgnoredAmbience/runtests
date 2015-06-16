from __future__ import print_function
import logging
import os
import random
import sys

try:
    import classad
    import htcondor
except ImportError as e:
    classad = htcondor = None
    condor_import_error = e

class Condor(object):
    def condor_help(self):
        help_msg = """
Condor Help

This script is able to submit test run jobs to Condor, results may only be
recorded using the Postgres database option.

You require a working Condor installation on the local machine.
You may need to add the Condor Python binding libraries to your PYTHONPATH, eg:
  export PYTHONPATH=${PYTHONPATH}:${CONDOR_HOME}/lib/python

Imperial DoC users should place the following commands in their shell profile
to enable Condor support:
  export PATH=${PATH}:${CONDOR_HOME}/bin
  export LD_LIBRARY_PATH=${CONDOR_HOME}/lib/condor
  export PYTHONPATH=${PYTHONPATH}:${CONDOR_HOME}/lib/python

A full JSCert (Coq/OCaml) installation is not required for each machine the
tests are to be run on, you just need a working run_js executable in the interp
directory. (You should test this on an appropriate machine in the cluster
before a run). The run_js interpreter uses few shared libraries, so should
hopefully be portable between Linux distros without need for recompilation.

A Postgres database is required to collect results. Options as printed by
--help should be straightforward. A template Postgres configuration file is
available in the repo at /.pgconfig.example
If you've forgotten them, your Postgres username and password are usually kept
in the .pgpass file in your home directory, this testrunner makes no attempt to
read this file.

Sample command line to run tests on Condor:
  runtests.py --condor --db postgres --batch_size 4 tests/test262/

Note that for large test suites, such as test262, the Condor scheduler daemon
runs out of memory with >~5000 jobs. The batch size parameter groups multiple
(4 in this case) test cases into one Condor job to prevent an explosion in
memory. The memory use results from the way this script passes parameters to
Condor and the way Condor stores them, we should probably fix this...

The status of Condor jobs can be retrieved using the condor_q command. Jobs
that have become stuck can be removed using condor_rm.

Presently, the only way to interrogate the results is to perform SQL queries by
hand. The analysis scripts haven't yet been updated to support the new database
schema.
"""
        print(help_msg)
        print("Testing Condor Python bindings: ")
        self.condor_test_import()
        print("OK!")

    def condor_test_import(self):
        if not (classad or htcondor):
            logging.error("Could not load modules required for Condor submit support (see --condor_help): %s",
                    condor_import_error)
            exit(1)

    def condor_submit(self, job, machine_reqs, initial_args, random_sched, verbose=False):
        batches = job.get_batches()
        n = len(batches)

        batch_ids = map(lambda b: b._dbid, batches)
        batch_tcs = map(lambda b: b.get_testcases(), batches)
        tc_paths = map(lambda tcs: " ".join(map(lambda t: t.get_relpath(), tcs)), batch_tcs)
        tc_ids = map(lambda tcs: ",".join(map(lambda t: str(t._dbid), tcs)), batch_tcs)

        # Fetch the name of this machine in the condor cluster
        coll = htcondor.Collector()
        sched_classad = None
        if random_sched:
            scheds = coll.locateAll(htcondor.DaemonTypes.Schedd)
            scheds = [elem for elem in scheds if elem['DetectedMemory']>8000]
            sched_classad = random.choice(scheds)
            machine = sched_classad['Machine']
        else:
            machine = coll.locate(htcondor.DaemonTypes.Schedd)['Machine']

        fsdomain = coll.query(
            htcondor.AdTypes.Startd,
            'Machine =?= "%s"' % machine,
            ['FileSystemDomain']
        )[0]['FileSystemDomain']

        c = classad.ClassAd()
        # Custom attributes
        c['tests'] = tc_paths
        c['batchids'] = batch_ids
        c['testids'] = tc_ids

        # Standard job attributes
        c['AccountingGroup'] = 'jscert.' + job.user
        c['ShouldTransferFiles'] = 'IF_NEEDED'
        c['FileSystemDomain'] = fsdomain
        c['Owner'] = job.user
        c['JobUniverse'] = 5
        c['Requirements'] = classad.ExprTree(machine_reqs)
        c['Cmd'] = __file__
        c['Iwd'] = os.getcwd()

        if verbose:
            c['Out'] = "condor_logs/job_%s_condor_$$([ClusterId])-$$([ProcId]).out" % [job._dbid]
            c['Err'] = "condor_logs/job_%s_condor_$$([ClusterId])-$$([ProcId]).err" % [job._dbid]
            c['UserLog'] = "condor_logs/job_%s_condor_$$([ClusterId]).log" % [job._dbid]

        # Build argument string
        args_to_copy = ["db", "dbpath", "db_pg_schema", "interp", "interp_path",
                        "interp_version", "no_parasite", "debug", "verbose", "timeout", "parser"]

        arguments = ["--condor_run"]
        initial_args = vars(initial_args)
        for (arg, val) in initial_args.iteritems():
            if val and arg in args_to_copy:
                arguments.append("--%s" % arg)
                if not isinstance(val, bool):
                    # Condor is picky about quote types
                    arguments.append("'%s'" % val)
        arguments.append("$$([tests[ProcId]])")

        argstr =  ' '.join(arguments)
        c['Arguments'] = argstr
        logging.debug("Using argstr: %s" % argstr)

        # Build the environment
        env = dict(os.environ)
        env['_RUNTESTS_PROCID'] = "$$([ProcId])"
        env['_RUNTESTS_JOBID'] = job._dbid
        env['_RUNTESTS_BATCHID'] = "$$([batchids[ProcId]])"
        env['_RUNTESTS_TESTIDS'] = "$$([testids[ProcId]])"
        env['BISECT_FILE'] = "bisect_$$([ClusterId])-$$([ProcId])-"
        c['Environment'] = " ".join(map(lambda it: "%s='%s'" % it, env.iteritems()))

        if sched_classad:
            sched = htcondor.Schedd(sched_classad)
        else:
            sched = htcondor.Schedd()
        cluster_id = sched.submit(c, n)

        try:
            job.condor_scheduler = machine
        except RuntimeError as e:
            logging.error("The Condor scheduler appears to have failed. You should probably run condor_restart.")
            raise e
        job.condor_cluster = cluster_id

        return n

    def condor_update_job(self, job, dbmanager):
        job._dbid = int(os.environ['_RUNTESTS_JOBID'])
        batch = job.batches[0]
        batch._dbid = int(os.environ['_RUNTESTS_BATCHID'])
        batch.condor_proc = int(os.environ['_RUNTESTS_PROCID'])

        tc_ids = os.environ['_RUNTESTS_TESTIDS'].split(",")
        tcs = batch.get_testcases()
        for (tc, tc_id) in zip(tcs, tc_ids):
            tc._dbid = tc_id

        return batch
