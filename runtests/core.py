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

from .interpreter import Interpreter
from .main import JSCERT_ROOT_DIR
from .resulthandler import TestResultHandler
from .util import Timer
from . import dbmodels



class TestCase(dbmodels.TestCase):
    # List of required JS helper files for test to run (not db-persisted)
    includes = None

    def __init__(self, filename, lazy=False):
        self.filename = os.path.relpath(filename, JSCERT_ROOT_DIR)
        if not lazy:
            self.fetch_file_info()

    def fetch_file_info(self):
        if self.includes is None:
            with open(self.get_realpath()) as f:
                # If this was a sputnik test, it may have expected to fail.
                # If so, we will need to invert the return value later on.
                buf = f.read()
                self.negative = "@negative" in buf
                self.includes = re.findall(
                    '\$INCLUDE\([\'"]([^\)]+)[\'"]\)', buf)

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

    def get_relpath(self):
        """Return path of test relative to JSCert project repo root directory"""
        return self.filename

    def get_realpath(self):
        """Returns the real/absolute path to the test"""
        return os.path.join(JSCERT_ROOT_DIR, self.filename)

class TestRun(dbmodels.Run, Timer):

    """
    A test run knows what test case to run, whether it has been run and if so,
    whether it passed, failed or aborted, and what output it generated along the
    way.
    """

    # Fake-enum for result
    UNKNOWN = "UNKNOWN"
    PASS = "PASS"
    FAIL = "FAIL"
    ABORT = "ABORT"
    TIMEOUT = "TIMEOUT"

    # Test results
    result = UNKNOWN   # Derived from exit_code by an interpreter class
    exit_code = -1     # UNIX exit code
    stdout = ""
    stderr = ""

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
        return os.path.basename(self.testcase.filename)

    def get_result(self):
        return self.result

    def get_result_text(self):
        return self.result

    def passed(self):
        return self.result == TestCase.PASS

    def failed(self):
        return self.result == TestCase.FAIL

    def aborted(self):
        return self.result == TestCase.ABORT

    def timeout(self):
        return self.result == TestCase.TIMEOUT

    def report_dict(self):
        return {"testname": self.get_testname(),
                "filename": self.filename,
                "stdout": self.stdout,
                "stderr": self.stderr}

    # self.batch set by batch_id?

class TestBatch(dbmodels.Batch, Timer):

    """Information about a collection of TestCases to be run on a machine"""

    # @reconstructor
    def __init__(self):
        self.pending_tests = deque()
        self.passed_tests = []
        self.failed_tests = []
        self.aborted_tests = []

    def __len__(self):
        return len(self.pending_tests)

    def add_testcase(self, testcase):
        self.testcases.append(testcase)
        self.pending_tests.append(testcase)

    def add_testcases(self, testcases):
        self.testcases.extend(testcases)
        self.pending_tests.extend(testcases)

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


class Job(dbmodels.Job, Timer):

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
    _batch_size = 0
    batches = None

    def __init__(self, title, note, interpreter, batch_size=None):
        self.title = title
        self.note = note
        self.interpreter = interpreter
        self.create_time = datetime.now()
        self.impl_name = interpreter.get_name()
        self.impl_version = interpreter.get_version()
        self.set_repo_version()
        self.user = pwd.getpwuid(os.geteuid()).pw_name

        self._batch_size = batch_size

        # Lazily construct batches as required
        self.batches = []
        self.new_batch()

    def set_repo_version(self):
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=JSCERT_ROOT_DIR)
        self.repo_version = out.strip()

    def new_batch(self):
        self.batches.append(TestBatch(self))

    def add_testcase(self, testcase):
        if self._batch_size and len(self.batches[-1]) >= self._batch_size:
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
