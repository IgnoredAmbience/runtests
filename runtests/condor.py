"""Condor scheduler support for test running"""
from __future__ import print_function
import logging
import os
import re
import subprocess
import sys

from .db import DBManager
from .executor import Executor

try:
    import classad
    import htcondor
except ImportError as ex:
    classad = htcondor = None
    CONDOR_IMPORT_ERROR = ex


class Condor(Executor):

    # Default class selections, see argument help for details
    machine_reqs = 'OpSysMajorVer > 12'
    sub_exec = 'sequential'
    log_job = False
    log_all = False
    other_args = None

    __dbmanager__ = None

    def __init__(self, condor_req=machine_reqs, condor_exec=sub_exec,
                 condor_log=log_job, condor_log_all=log_all, **argv):
        super(Condor, self).__init__(**argv)
        self.machine_reqs = condor_req
        self.sub_exec = condor_exec
        self.log_job = condor_log
        self.log_all = condor_log_all

        # Cache all other passed args for the argument string the executed job
        self.other_args = argv

    def add_handler(self, handler):
        if isinstance(handler, DBManager):
            self.__dbmanager__ = handler
        super(Condor, self).add_handler(handler)

    def run_job(self, job):
        # Submit job to Condor?
        jobstr = self.build_job(job)

        print("Submitting to Condor Scheduler")

        if False:
            self.write_cmd(jobstr)
            job.condor_scheduler = "condor.cmd file"
        else:
            job.condor_cluster = self.submit_job(jobstr)
            job.condor_scheduler = os.uname()[1]

        print("Submitted %s batches as cluster %s on %s. Test job id: %s" %
              (len(job.batches), job.condor_cluster, job.condor_scheduler, job._dbid))

        if self.__dbmanager__:
            self.__dbmanager__.update_object(job)
            self.__dbmanager__.disconnect()
        exit(0)

    def build_job(self, job):
        # Batch and testcase information :: What to run
        n = len(job.batches)

        c = {
            'universe': 'vanilla',
            'requirements': self.machine_reqs,
            'executable': sys.argv[0],
            'accounting_group': 'jscert.' + job.user,
            'getenv': 'True',    # Copy environment variables across
            'arguments': '"%s"' % (self.build_arguments(job).replace('"', '""'))
        }

        if self.log_all:
            c['output'] = "job_%s_condor_$(Cluster)-$(Process).out" % \
                job._dbid
            c['error'] = "job_%s_condor_$(Cluster)-$(Process).err" % \
                job._dbid

        if self.log_job:
            c['log'] = "job_%s_condor_$(Cluster).log" % job._dbid

        jobstr = '\n'.join('%s = %s\n' % (k, v) for (k, v) in c.iteritems())
        jobstr += '\nqueue %s' % n

        return jobstr

    def write_cmd(self, jobstr):
        with open('condor.cmd', 'w') as f:
            f.writelines(jobstr)

    def submit_job(self, jobstr):
        p = subprocess.Popen(['condor_submit', '-terse', '-'],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=sys.stderr)
        (out, err) = p.communicate(jobstr)
        match = re.search(r'(\d+)\.\d+ - \d+\.\d+', out)
        if match:
            return match.group(1)
        return 0

    def build_arguments(self, job):
        # Build argument string
        args_to_copy = [
            "db",
            "dbpath",
            "db_pg_schema",
            "interp",
            "interp_path",
            "interp_version",
            "no_parasite",
            "parser",
            "verbose",
            "timeout",
            "simp",
            "stats",
        ]

        arguments = []
        for (arg, val) in self.other_args.iteritems():
            if val and arg in args_to_copy:
                arguments.append("--%s" % arg)
                if not isinstance(val, bool):
                    # Condor is picky about quote types
                    v = str(val).replace("'", "''")
                    arguments.append("'%s'" % v)

        # Executor to use for batches
        arguments.append("-x")
        arguments.append(self.sub_exec)

        # Batch to run
        arguments.append("--batch")
        arguments.append("%s,$(Process)" % job._dbid)

        return ' '.join(arguments)

    @staticmethod
    def add_arg_group(argp):
        condor_args = argp.add_argument_group(title="Condor Options (use with "
                                              "-x condor)")

        condor_args.add_argument(
            "--condor_req", action="store", metavar="reqs",
            default=Condor.machine_reqs,
            help='ClassAd describing minimum requirements for machines jobs '
            'are to run on, defaults to ICDoC minimum')

        condor_args.add_argument(
            "--condor_exec", "-X", action="store", default=Condor.sub_exec,
            choices=Executor.TypesStr().remove('condor'),
            help='Executor type to use for each individual batch (default: '
            'sequential)')

        condor_args.add_argument(
            "--condor_log", action="store_true",
            help='Produce a logfile for the Condor job')

        condor_args.add_argument(
            "--condor_log_all", action="store_true",
            help='Produce a logfile for each Condor test run')

        condor_args.add_argument(
            "--condor_help", action="store_true", help="Help on Condor setup")

    @staticmethod
    def condor_help():
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
        Condor.condor_test_import()
        print("OK!")

    @staticmethod
    def condor_test_import():
        if not (classad or htcondor):
            logging.error("Could not load modules required for Condor support "
                          "(see --condor_help): %s", CONDOR_IMPORT_ERROR)
            exit(1)
