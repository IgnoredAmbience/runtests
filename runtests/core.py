from collections import deque
from datetime import datetime
import os
import pwd
import re
import sys
import time

from .db import DBObject
from .interpreter import Interpreter
from .resulthandler import TestResultHandler
from .util import Timer, get_git_version
from .parseTestRecord import parseTestRecord


class TestCase(Timer, DBObject):

    """
    A test case knows what file it came from, whether it has been run and if so,
    whether it passed, failed or aborted, and what output it generated along the
    way.
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
    test_record_loaded = False
    negative = False   # Whether the testcase is expected to fail
    nostrict = False
    onlystrict = False
    includes = None    # List of required JS helper files for test to run

    # Test results
    result = UNKNOWN   # Derived from exit_code by an interpreter class
    exit_code = -1     # UNIX exit code
    stdout = ""
    stderr = ""


    def __init__(self, filename, lazy=False):
        self.filename = filename
        self.realpath = os.path.realpath(filename)
        if not lazy:
            self.fetch_file_info()

    def fetch_file_info(self):
        if not self.test_record_loaded:
            with open(self.get_realpath()) as f:
                buf = f.read()
                test_record = parseTestRecord(buf, self.filename)
                self.negative = 'negative' in test_record
                self.onlystrict = 'onlyStrict' in test_record
                self.nostrict = 'noStrict' in test_record or 'raw' in test_record
                if test_record.get('includes'):
                    self.includes = test_record['includes']
                else:
                    self.includes = []

                self.test_record_loaded = True

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
        """Return path of test"""
        return self.filename

    def get_realpath(self):
        """Returns the real/absolute path to the test"""
        return self.realpath

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
             "duration": self.get_delta()}
        if self.batch:
            d['batch_id'] = self.batch._dbid
            self.batch.add_job_id(d)
        return d

    def db_tc_dict(self):
        return {"id": self.get_relpath(),
                "negative": self.negative,
                "onlystrict": self.onlystrict,
                "nostrict": self.nostrict}

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

    """Information about a collection of TestCases to be run on a machine"""
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

    def add_job_id(self, d):
        if self.job is not None:
            d['job_id'] = self.job._dbid

    def _db_dict(self):
        d = {"system": self.system,
             "osnodename": self.osnodename,
             "osrelease": self.osrelease,
             "osversion": self.osversion,
             "hardware": self.hardware,
             "start_time": self.start_time,
             "end_time": self.stop_time,
             "condor_proc": self.condor_proc}
        self.add_job_id(d)
        return d


class Job(Timer, DBObject):

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
        self.set_repo_version()
        self.impl_version = interpreter.get_version()
        self.user = pwd.getpwuid(os.geteuid()).pw_name
        self.tests_version = None

        self._batch_size = batch_size

        # Lazily construct batches as required
        self.batches = []
        self.new_batch()

    def set_repo_version(self):
        if "CI_BUILD_REF" in os.environ:
            self.repo_version = os.environ["CI_BUILD_REF"]
        else:
            self.repo_version = get_git_version()

    def set_tests_version(self, dir):
        self.tests_version = get_git_version(dir)

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
                "condor_scheduler": self.condor_scheduler,
                "tests_version": self.tests_version}
