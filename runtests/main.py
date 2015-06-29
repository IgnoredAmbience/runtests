#!/usr/bin/env python
"""
A not-so-mini test harness. Runs all the files you specify through an interpreter
you specify, and collates the exit codes for you. Call with the -h switch to
find out about options.
"""
from __future__ import print_function
import argparse
import logging
import os
import signal
from functools import reduce

JSCERT_ROOT_DIR = os.path.realpath(
    os.path.join(os.path.dirname(__file__), "..", ".."))

from .condor import *
from .core import *
from .db import *
from .interpreter import *
from .resulthandler import *


class Runtests(object):

    """Main class"""

    db = None

    interrupted = False

    def get_testcases_from_paths(self, paths, testcases=[], exclude=[]):
        return reduce(
            lambda ts, p: self.get_testcases_from_path(p, ts, exclude),
            paths, [])

    def get_testcases_from_path(self, path, testcases=[], exclude=[]):
        path = os.path.realpath(path)
        if not os.path.exists(path):
            raise IOError("No such file or directory: %s" % path)

        if os.path.isdir(path):
            return self.get_testcases_from_dir(path, testcases, exclude)
        elif not path in exclude:
            testcases.append(TestCase(path))

        return testcases

    def get_testcases_from_dir(self, dirname, testcases=[], exclude=[]):
        """Recusively walk the given directory looking for .js files, does not traverse symbolic links"""
        dirname = os.path.realpath(dirname)
        for r, d, f in os.walk(dirname):
            for filename in f:
                filename = os.path.join(r, filename)
                if os.path.isfile(filename) and filename.endswith(".js") and not filename in exclude:
                    testcases.append(TestCase(filename))
        return testcases

    def interrupt_handler(self, signal, frame):
        if self.interrupted:
            logging.warning("Terminating, please be patient...")
            return

        logging.warning("Interrupted... Running pending output actions")
        self.interrupted = True
        self.executor.stop()

        exit(2)

    def build_arg_parser(self):
        # Our command-line interface
        argp = argparse.ArgumentParser(
            fromfile_prefix_chars='@',
            description="""
Run some tests with some JS implementation: by default, with JSRef.

Most options below should be self explanatory.
This script also can generate html reports of the test jobs and log test
results into a database (Postgres or SQLite) for further analysis.

Testcases can either be run sequentially on the local machine or
scheduled to run in parallel on a Condor computing cluster.

To include the contents of a file as commandline arguments, prefix the
filename using the @ character.
""")

        argp.add_argument(
            "filenames", metavar="path", nargs="*",
            help="The test file or directory we want to run. If a directory is "
            "provided, .js files will be searched for recursively.")

        argp.add_argument(
            "--timeout", action="store", metavar="timeout",
            type=int, default=None,
            help="Timeout in seconds for each testcase, defaults to None.")

        argp.add_argument(
            "--exclude", action="append", metavar="file",
            type=os.path.realpath, default=[],
            help="Files in test tree to exlude from testing")

        argp.add_argument(
            "--verbose", '-v', action="count",
            help="Print the output of the tests as they happen. Pass multiple "
            "times for more verbose output.")

        argp.add_argument(
            '--executor', '-x', action='store',
            choices=Executor.TypesStr(), default='sequential',
            help='Execution strategy to use (default: sequential)')

        condor_args.add_argument(
            "--batch_size", action="store", metavar="n", default=0, type=int,
            help="Number of testcases to run per batch (default value varies"
            " depending on the executor used)")


        # Test Job information
        jobinfo = argp.add_argument_group(title="Test job metadata")

        jobinfo.add_argument(
            "--title", action="store", metavar="string", default="",
            help="Optional title for this test.")

        jobinfo.add_argument(
            "--note", action="store", metavar="string", default="",
            help="Optional explanatory note to be added to the test report.")

        interp_grp = argp.add_argument_group(title="Interpreter options")
        interp_grp.add_argument(
            "--interp", action="store",
            choices=Interpreter.TypesStr(), default="jsref",
            help="Interpreter type (default: jsref)")

        interp_grp.add_argument(
            "--interp_path", action="store", metavar="path", default="",
            help="Path to the interpreter (some types have default values)")

        interp_grp.add_argument(
            "--parser", action="store", metavar="path", default="",
            help="Override path to parser (JSRef only)")

        interp_grp.add_argument(
            "--interp_version", action="store", metavar="version", default="",
            help="The version of the interpreter you're running. (optional, "
            "value will be auto-detected if not provided)")

        interp_grp.add_argument("--jsonparser", action="store_true",
                                help="Use the JSON parser (Esprima) when running tests.")

        interp_grp.add_argument("--no_parasite", action="store_true",
                                help="Run JSRef with -no-parasite flag")

        report_grp = argp.add_argument_group(title="Report Options")
        report_grp.add_argument(
            "--webreport", action="store_true",
            help="Produce a web-page of your results in the default web "
            "directory. Requires pystache.")

        report_grp.add_argument(
            "--templatedir", action="store", metavar="path",
            default=os.path.join("test_reports"),
            help="Where to find our web-templates when producing reports")

        report_grp.add_argument(
            "--reportdir", action="store", metavar="path",
            default=os.path.join("test_reports"),
            help="Where to put our test reports")

        report_grp.add_argument(
            "--noindex", action="store_true",
            help="Don't attempt to build an index.html for the reportdir")

        # Database config
        db_args = argp.add_argument_group(title="Database options")
        db_args.add_argument(
            "--db", action="store", choices=['sqlite', 'postgres'],
            help="Save the results of this testrun to the database")

        db_args.add_argument(
            "--dbpath", action="store", metavar="file", default="",
            help="Path to the database (for SQLite) or configuration file (for "
            "Postgres).")

        db_args.add_argument("--db_init", action="store_true",
                             help="Create the database and load schema")

        db_args.add_argument(
            "--db_pg_schema", action="store", metavar="name", default="jscert",
            help="Schema of Postgres database to use. (Defaults to 'jscert')")

        return argp

    def main(self):
        # Parse arguments
        argp = self.build_arg_parser()
        for executor in Executor.Types():
            executor.add_arg_group(argp)
        args = argp.parse_args()

        # Configure logging
        log_level = logging.DEBUG if args.verbose > 1 else logging.WARNING
        logging.basicConfig(level=log_level)

        # What to do if the user hits control-C
        signal.signal(signal.SIGINT, self.interrupt_handler)

        self.executor = executor = Executor.Construct(args.executor, args)

        # Output handlers
        cli = CLIResultPrinter(args.verbose)
        executor.add_handler(cli)

        if args.webreport:
            webreport_handler =
                WebResultPrinter(args.templatedir, args.reportdir, args.noindex)
            executor.add_handler(webreport_handler)

        # Interpreter
        interpreter = Interpreter.Construct(args.interp, args)
        interpreter.no_parasite = args.no_parasite
        interpreter.jsonparser = args.jsonparser
        interpreter.set_parser(args.parser)
        interpreter.set_path(args.interp_path)
        interpreter.set_version(args.interp_version)
        interpreter.set_timeout(args.timeout)

        job = Job(args.title, args.note, interpreter)

        # Generate testcases
        logging.info("Finding test cases to run")
        testcases = self.get_testcases_from_paths(
            args.filenames, exclude=args.exclude)

        job.add_testcases(testcases)
        logging.info("%s tests found, split into %s test batches.",
                     len(testcases), len(job.batches))

        executor.run_job(job)

        exit(cli.get_exit_code())

if __name__ == "__main__":
    Runtests().main()
