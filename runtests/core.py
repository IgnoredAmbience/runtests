from collections import deque
from datetime import datetime
import os
import pwd
import re
import sys
import time

if sys.version_info < (3, 3):
    # Use backported subprocess stdlib for timeout functionality
    import subprocess32 as subprocess
else:
    import subprocess

from .db import DBObject
from .interpreter import Interpreter
from .main import JSCERT_ROOT_DIR
from .resulthandler import TestResultHandler
from .util import Timer

class TestCase(Timer, DBObject):

    """
    A test case knows what file it came from, whether it has been run and if so,
    whether it passed, failed or aborted, and what output it generated along the way.
    """
    _table = "test_runs"
    batch = None

    # Fake-enum for result
    UNKNOWN = 0
    PASS = 1
    FAIL = 2
    ABORT = 3
    TIMEOUT = 4
    RESULT_TEXT = ["UNKNOWN", "PASS", "FAIL", "ABORT", "TIMEOUT"]

    filename = ""
    negative = False   # Whether the testcase is expected to fail
    includes = None    # List of required JS helper files for test to run

    # Test results
    result = UNKNOWN   # Derived from exit_code by an interpreter class
    exit_code = -1     # UNIX exit code
    stdout = ""
    stderr = ""

    def __init__(self, filename, lazy=False):
        self.filename = os.path.relpath(filename, JSCERT_ROOT_DIR)
        if not lazy:
            self.fetch_file_info()

    def fetch_file_info(self):
        if self.includes == None:
            with open(self.get_realpath()) as f:
                # If this was a sputnik test, it may have expected to fail.
                # If so, we will need to invert the return value later on.
                buf = f.read()
                self.negative = "@negative" in buf
                self.includes = re.findall(
                    '\$INCLUDE\([\'"]([^\)]+)[\'"]\)', buf)

    def set_result(self, interp_result, exit_code, stdout, stderr):
        self.interp_result = interp_result

        if interp_result == Interpreter.ABORT:
            self.result = TestCase.ABORT
        elif interp_result == Interpreter.TIMEOUT:
            self.result = TestCase.TIMEOUT
        elif self.negative:
            if interp_result == Interpreter.PASS:
                self.result = TestCase.FAIL
            else:
                self.result = TestCase.PASS
        else:
            if interp_result == Interpreter.PASS:
                self.result = TestCase.PASS
            else:
                self.result = TestCase.FAIL

        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    def get_testname(self):
        return os.path.basename(self.filename)

    def get_result(self):
        return self.result

    def get_result_text(self):
        return self.RESULT_TEXT[self.result]

    def passed(self):
        return self.result == self.PASS

    def failed(self):
        return self.result == self.FAIL

    def aborted(self):
        return self.result == self.ABORT

    def timeout(self):
        return self.result == self.TIMEOUT

    def get_relpath(self):
        """Returns path of test relative to JSCert project repo root directory"""
        return self.filename

    def get_realpath(self):
        """Returns the real/absolute path to the test"""
        return os.path.join(JSCERT_ROOT_DIR, self.filename)

    def report_dict(self):
        return {"testname": self.get_testname(),
                "filename": self.filename,
                "stdout": self.stdout,
                "stderr": self.stderr}

    def _db_dict(self):
        d = {"test_id": self.get_relpath(),
             "result": self.get_result_text(),
             "exit_code": self.exit_code,
             "stdout": self.stdout,
             "stderr": self.stderr,
             "duration": self.get_duration()}
        if self.batch:
            d['batch_id'] = self.batch._dbid
        return d

    def db_tc_dict(self):
        return {"id": self.get_relpath(),
                "negative": self.negative}

    def is_negative(self):
        self.fetch_file_info()
        return self.negative

    def get_includes(self):
        self.fetch_file_info()
        return self.includes

    # Does this test try to load other libraries?
    def usesInclude(self):
        return len(self.get_includes()) > 0

    def isLambdaS5Test(self):
        return self.get_relpath().startswith("tests/LambdaS5/unit-tests/")

    def isSpiderMonkeyTest(self):
        return self.get_relpath().startswith("tests/SpiderMonkey/")



class TestBatch(Timer, DBObject):

    """Information about a collection of TestCases to be run on a machine together"""

    _table = "test_batches"
    job = None

    # Machine info
    system = ""
    osnodename = ""
    osrelease = ""
    osversion = ""
    hardware = ""

    condor_proc = -1

    pending_tests = None

    # Classified test cases
    passed_tests = None
    failed_tests = None
    aborted_tests = None

    def __init__(self, job):
        self.pending_tests = deque()
        self.passed_tests = []
        self.failed_tests = []
        self.aborted_tests = []
        self.job = job

    def __len__(self):
        return len(self.pending_tests)

    def add_testcase(self, testcase):
        self.pending_tests.append(testcase)
        testcase.batch = self

    def add_testcases(self, testcases):
        self.pending_tests.extend(testcases)
        for tc in testcases:
            tc.batch = self

    def has_testcase(self):
        return len(self.pending_tests) > 0

    def get_testcase(self):
        return self.pending_tests.popleft()

    def get_testcases(self):
        return self.pending_tests

    def get_finished_testcases(self):
        return self.passed_tests + self.failed_tests + self.aborted_tests

    def set_machine_details(self):
        (self.system, self.osnodename, self.osrelease,
         self.osversion, self.hardware) = os.uname()

    def test_finished(self, testcase):
        if testcase.passed():
            self.passed_tests.append(testcase)
        elif testcase.failed():
            self.failed_tests.append(testcase)
        else:
            self.aborted_tests.append(testcase)

    def make_report(self):
        return {"testtitle": self.job.title,
                "testnote": self.job.note,
                "implementation": self.job.impl_name,
                "system": self.system,
                "timetaken": self.get_duration(),
                "osnodename": self.osnodename,
                "osrelease": self.osrelease,
                "osversion": self.osversion,
                "hardware": self.hardware,
                "time": time.asctime(time.gmtime()),
                "user": self.job.user,
                "numpasses": len(self.passed_tests),
                "numfails": len(self.failed_tests),
                "numaborts": len(self.aborted_tests),
                "aborts": map(lambda x: x.report_dict(), self.aborted_tests),
                "failures": map(lambda x: x.report_dict(), self.failed_tests),
                "passes": map(lambda x: x.report_dict(), self.passed_tests)}

    def _db_dict(self):
        d = {"system": self.system,
             "osnodename": self.osnodename,
             "osrelease": self.osrelease,
             "osversion": self.osversion,
             "hardware": self.hardware,
             "start_time": self.start_time,
             "end_time": self.stop_time,
             "condor_proc": self.condor_proc}
        if self.job != None:
            d['job_id'] = self.job._dbid
        return d

class Job(DBObject):

    """Information about a particular test job, a collection of TestBatches"""

    _table = "test_jobs"
    title = ""
    note = ""
    impl_name = ""
    impl_version = ""
    repo_version = ""
    create_time = None
    user = ""
    condor_cluster = 0
    condor_scheduler = ""

    interpreter = None

    """
    batch_size of 0 indicates a single batch containing all tests
    n>0 produces batches of size n
    """
    batch_size = 0
    batches = None

    def __init__(self, title, note, interpreter, batch_size=0):
        self.title = title
        self.note = note
        self.interpreter = interpreter
        self.create_time = datetime.now()
        self.impl_name = interpreter.get_name()
        self.impl_version = interpreter.get_version()
        self.set_repo_version()
        self.user = pwd.getpwuid(os.geteuid()).pw_name
        self.batch_size = batch_size
        self.batches = []
        self.new_batch()

    def set_repo_version(self):
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=JSCERT_ROOT_DIR)
        self.repo_version = out.strip()

    def new_batch(self):
        self.batches.append(TestBatch(self))

    def add_testcase(self, testcase):
        if self.batch_size and len(self.batches[-1]) >= self.batch_size:
            self.new_batch()
        self.batches[-1].add_testcase(testcase)

    def add_testcases(self, testcases):
        for testcase in testcases:
            self.add_testcase(testcase)

    def _db_dict(self):
        return {"title": self.title,
                "note": self.note,
                "impl_name": self.impl_name,
                "impl_version": self.impl_version,
                "create_time": self.create_time,
                "repo_version": self.repo_version,
                "username": self.user,
                "condor_cluster": self.condor_cluster,
                "condor_scheduler": self.condor_scheduler}

class Executor(object):
    """Base class for different test execution strategies, for example:
    sequential, multi-threaded, distributed with Condor"""

    stopping = False
    test_result_handlers = None

    def __init__(self):
        self.handlers = []

    def add_handler(self, handler):
        if not isinstance(handler, TestResultHandler):
            raise TypeError("%s is not a TestResultHandler" % (handler,))
        self.test_result_handlers.append(handler)

    def run_job(self, job):
        """Override this method to implement a custom test batch dispatch"""

        for handler in self.handlers:
            handler.start_job(job)

        job.start_timer()
        for batch in job.batches:
            self.run_batch(batch)
        job.stop_timer()

        for handler in self.handlers:
            handler.finish_job(job)

    def run_batch(self, batch):
        batch.set_machine_details()

        for handler in self.handlers:
            handler.start_batch(batch)

        batch.start_timer()

        # Now let's get down to the business of running the tests
        while batch.has_testcase():
            testcase = batch.get_testcase()
            for handler in self.handlers:
                handler.start_test(testcase)

            # FIXME: Too much indirection
            batch.job.interpreter.run_test(testcase)

            # FIXME: move this closer to run_test? Or testcase?
            batch.test_finished(testcase)

            # Inform handlers of a test result
            # We share the same TestResult among handlers
            for handler in self.handlers:
                handler.finish_test(testcase)

        batch.stop_timer()

        # Tell handlers that we're done
        for handler in self.handlers:
            handler.finish_batch(batch)

    def stop(self):
        if self.stopping:
            return

        self.stopping = True

        # TODO: Stop stuff

        for handler in self.handlers:
            handler.interrupt_handler()
