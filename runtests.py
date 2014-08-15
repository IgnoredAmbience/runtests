#!/usr/bin/env python
"""
A not-so-mini test harness. Runs all the files you specify through an interpreter
you specify, and collates the exit codes for you. Call with the -h switch to
find out about options.
"""
import sys
import os
import signal
import subprocess
import getpass
from datetime import datetime, time
import re
import urllib
from collections import deque
import pwd
import argparse

JSCERT_ROOT_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
DB_SCHEMA_LOCATION = os.path.join(JSCERT_ROOT_DIR, 'test_data', 'createTestDB.sql')
DEBUG=False
VERBOSE=False

# Some handy data structures

class Timer(object):
    start_time = datetime.min
    stop_time = datetime.min

    def start_timer(self):
        self.start_time = datetime.now()

    def stop_timer(self):
        self.stop_time = datetime.now()

    def get_delta(self):
        return self.stop_time - self.start_time

    def get_duration(self):
        return self.get_delta().total_seconds()

class DBObject(object):
    _table = ""
    _dbid = 0

    def db_dict(self):
        dic = self._db_dict()
        if self._dbid:
            dic['id'] = self._dbid
        return dic

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
    RESULT_TEXT = ["UNKNOWN","PASS","FAIL","ABORT"]

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
                self.includes = re.findall('\$INCLUDE\([\'"]([^\)]+)[\'"]\)', buf)

    def set_result(self, interp_result, exit_code, stdout, stderr):
        self.interp_result = interp_result

        if interp_result == Interpreter.ABORT:
            self.result = TestCase.ABORT
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

class TestResultHandler(object):
    """
    Recieves notifications of events in the test cycle

    A test is the execution of an individual test file
    A test batch it is a number of sequential executions of tests
    A test job is a collection of test batches, it may only use one interpreter
    """
    def start_batch(self, batch):
        """Called before the first test is run from a particular batch"""
        pass

    def start_test(self, test):
        """Called before each test is run"""
        pass

    def finish_test(self, test):
        """Called after each test is run"""
        pass

    def finish_batch(self, batch):
        """Called after the last test from a batch is run"""
        pass

    def interrupt_handler(self, signal, frame):
        """Called on a handler when the test run is terminating due to SIGINT"""
        pass

class DBManager(TestResultHandler):
    conn = None
    cur = None
    wait_for_batch = False

    def __del__(self):
        self.disconnect()

    def connect(self):
        """Only implement for db backends with limited connection pools"""
        pass

    def disconnect(self):
        """Only implement for db backends with limited connection pools, or require explicit commit"""
        pass

    def insert_testcases(self, testcases):
        """Bulk inserts testcase data and commits"""
        tcds = map(lambda t: t.db_tc_dict(), testcases)
        self.insert_ignore_many("test_cases", tcds)

    def create_job_batches_runs(self, job):
        self.insert_object(job)
        for batch in job.get_batches():
            self.insert_object(batch)
            for test in batch.get_testcases():
                self.insert_object(test)
        self.conn.commit()

    def start_batch(self, batch):
        self.connect()
        self.update_object(batch)
        self.conn.commit()
        if self.wait_for_batch:
            self.disconnect()

    def start_test(self, testcase):
        pass

    def finish_test(self, testcase):
        if not self.wait_for_batch:
            self.update_object(testcase)
            self.conn.commit()

    def finish_batch(self, batch):
        self.connect()
        if self.wait_for_batch:
            self.update_objects(batch.get_finished_testcases())
        self.update_object(batch)
        self.conn.commit()
        self.disconnect()

    # Helper functions
    def build_fields_insert(self, fields):
        """
        Builds a field list pattern to substitute into a SQL statement, eg:
        ["a","b","c"] ==> [ "a, b, c", ":a, :b, :c" ]
        """
        key_pairs = map(lambda k: (k, self.subst_pattern(k)), fields)
        key_lists = zip(*key_pairs)
        key_strings = map(", ".join, key_lists)
        return key_strings

    def build_fields_update(self, fields):
        """
        Builds a field list pattern to substitute into a SQL statement, eg:
        ["a","b","c"] ==> [ "a = :a, b = :b, c = :c" ]
        """
        assigns = map(lambda k: "%s = %s" % (k, self.subst_pattern(k)), fields)
        return ", ".join(assigns)

    def insert(self, table, dic):
        """Retrieval of inserted id is implementation-specific"""
        raise NotImplementedError

    def insert_many(self, table, coll):
        (fnames, fsubst) = self.build_fields_insert(coll[0].keys())
        sql = ("INSERT INTO %s (%s) VALUES (%s)" % (table, fnames, fsubst))
        self.cur.executemany(sql, coll)

    def insert_ignore_many(self, table, coll):
        """Insert or ignore row with colliding ID and commits"""
        raise NotImplementedError

    def insert_object(self, obj):
        if not obj._table:
            raise Exception("Object not suitable for database insertion")
        else:
            obj._dbid = self.insert(obj._table, obj.db_dict())

    def update(self, table, dic):
        if "id" not in dic:
            raise Exception("Needs id field")
        self.update_many(table, [dic])

    def update_many(self, table, coll):
        """Expects dbid to be set on all dicts being passed in for updating"""
        assigns = self.build_fields_update(coll[0].keys())
        sql = ("UPDATE %s SET %s WHERE id = %s" % (table, assigns, self.subst_pattern("id")))
        self.cur.executemany(sql, coll)

    def update_object(self, obj):
        if not obj._table:
            raise Exception("Object not suitable for database insertion")
        else:
            self.update(obj._table, obj.db_dict())

    def update_objects(self, objs):
        """Assumes all objects passed in are of same class"""
        table = objs[0]._table
        dicts = map(lambda o: o.db_dict(), objs)
        self.update_many(table, dicts)

    def import_schema(self):
        with open(DB_SCHEMA_LOCATION, 'r') as f:
            sql = f.read()
        sql = self.prepare_schema(sql)
        self.execute_script(sql)
        self.conn.commit()

    def execute_script(self, sql):
        self.cur.execute(sql)

    def prepare_schema(self, sql):
        return sql

class SQLiteDBManager(DBManager):
    def __init__(self, path, initing=False):
        import sqlite3

        if not initing and not os.path.isfile(path):
            raise Exception("Database not found at %s\nPlease create the database using --db_init before using it." % path)
        self.conn = sqlite3.connect(path)
        self.cur = self.conn.cursor()

    def subst_pattern(self, field):
        return (":%s" % field)

    def insert(self, table, dic):
        (fnames, fsubst) = self.build_fields_insert(dic.keys())
        sql = ("INSERT INTO %s (%s) VALUES (%s)" % (table, fnames, fsubst))
        self.cur.execute(sql, dic)
        return self.cur.lastrowid

    def insert_ignore_many(self, table, coll):
        """Insert or ignore rows with colliding ID and commits"""
        (fnames, fsubst) = self.build_fields_insert(coll[0].keys())
        sql = ("INSERT OR IGNORE INTO %s (%s) VALUES (%s)" % (table, fnames, fsubst))
        self.cur.executemany(sql, coll)
        self.conn.commit()

    def execute_script(self, sql):
        self.cur.executescript(sql)

class PostgresDBManager(DBManager):
    connstr = ""
    schema = ""

    def __init__(self, connstr, schema=""):
        import psycopg2
        self.connstr = connstr
        self.schema = schema

    def connect(self):
        import psycopg2
        if (not self.conn) or (self.conn.closed != 0):
            self.conn = psycopg2.connect(self.connstr)
            self.cur = self.conn.cursor()
            if self.schema:
                self.cur.execute("SET SCHEMA %s", (self.schema,))
                self.conn.commit()

    def disconnect(self):
        if self.cur:
            self.cur.close()
            self.cur = None
        if self.conn:
            self.conn.commit()
            self.conn.close()
            self.conn = None

    def subst_pattern(self, field):
        return ("%%(%s)s" % field)

    def insert(self, table, dic):
        (fnames, fsubst) = self.build_fields_insert(dic.keys())
        sql = ("INSERT INTO %s (%s) VALUES (%s) RETURNING id" % (table, fnames, fsubst))
        self.cur.execute(sql, dic)
        return self.cur.fetchone()[0]

    def insert_ignore_many(self, table, coll):
        """Insert or ignore rows with colliding ID, and commits"""
        (fnames, fsubst) = self.build_fields_insert(coll[0].keys())
        sql = ("INSERT INTO %s (%s) SELECT %s WHERE NOT EXISTS (SELECT 1 FROM %s WHERE id = %s)" %
               (table, fnames, fsubst, table, self.subst_pattern("id")))

        self.cur.execute("LOCK TABLE %s IN SHARE ROW EXCLUSIVE MODE" % table)
        self.cur.executemany(sql, coll)
        self.conn.commit()

    def prepare_schema(self, sql):
        if self.schema:
            try:
                self.cur.execute("CREATE SCHEMA %s" % (self.schema,))
            except psycopg2.ProgrammingError as e:
                raise Exception("Could not create schema: %s" % (e,))
        sql = re.sub(r"/\*\*\* POSTGRES ONLY \*\*\* (.*) \*\*\*/", r"\1", sql)
        sql = re.sub(r"(.*)integer(.*) autoincrement", r"\1serial\2", sql)
        return sql

class CLIResultPrinter(TestResultHandler):
    # Some pretty colours for our output messages.
    NORMAL = "\033[00m"
    HEADING = "\033[35m"
    PASS = "\033[32m"
    FAIL = "\033[31m"
    ABANDON = "\033[33m"

    verbose = False

    def __init__(self, verbose=False):
        self.verbose = verbose

    def start_test(self, testcase):
        self.print_heading(testcase.filename)

    def finish_test(self, testcase):
        if testcase.passed():
            self.print_pass("Passed!")
        elif testcase.failed():
            self.print_fail("Failed :/")
        elif testcase.aborted():
            self.print_abandon("Aborted...")
        else:
            print self.ABANDON+"Something really weird happened"+self.NORMAL
        if self.verbose:
            print "Exit code: %s" % (testcase.exit_code,)
            print "Test is negative? %s" % (testcase.is_negative(),)
            print "=== STDOUT ==="
            print testcase.stdout
            print "=== STDERR ==="
            print testcase.stderr

    def print_heading(self,s):
        print self.HEADING+s+self.NORMAL
    def print_pass(self,s):
        print self.PASS+s+self.NORMAL
    def print_fail(self,s):
        print self.FAIL+s+self.NORMAL
    def print_abandon(self,s):
        print self.ABANDON+s+self.NORMAL

    def finish_batch(self, batch):
        if len(batch.failed_tests) > 0:
            print "The following tests failed:"
            for failure in batch.failed_tests:
                print failure.filename
        if len(batch.aborted_tests) > 0:
            print "The following tests were abandoned"
            for abandoned in batch.aborted_tests:
                print abandoned.filename
        print ("There were %d passes, %d fails, and %d abandoned tests." %
            (len(batch.passed_tests), len(batch.failed_tests), len(batch.aborted_tests)))

class WebResultPrinter(TestResultHandler):
    """
    This class maintains the results of our test run, and generates a html report
    """

    # Configuration
    templatedir = ""
    reportdir = ""
    noindex = False

    def __init__(self, templatedir, reportdir, noindex):
        try:
            import pystache
        except ImportError as e:
            raise ImportError("%s: pystache is required for web reports" % e.message)

        self.noindex = noindex
        self.set_paths(templatedir, reportdir)

    def set_paths(self, templatedir, reportdir):
        """Check all files required for html output exist before we begin"""
        templates = ["template.tmpl","test_results.tmpl"]
        if not self.noindex:
            templates.append("index.tmpl")

        for f in templates:
            p = os.path.join(templatedir, f)
            if not os.access(p, os.R_OK):
                raise Exception("Required html template %s is not readable." % p)

        if not os.access(reportdir, os.W_OK):
            raise Exception("Report output directory %s is not writable." % reportdir)
        if not self.noindex:
            p = os.path.join(reportdir, "index.html")
            if os.path.isfile(p) and not os.access(p, os.W_OK):
                raise Exception("Report index file %s not writable." % p)

        self.templatedir = templatedir
        self.reportdir = reportdir

    def finish_batch(self, batch):
        self.produce_web_page(batch.make_report())

    def produce_web_page(self, report):
        import pystache

        simplerenderer = pystache.Renderer(escape = lambda u: u)
        with open(os.path.join(self.templatedir,"template.tmpl"),"r") as outer:
            with open(os.path.join(self.templatedir,"test_results.tmpl"),"r") as template:
                outfilenamebits = ["report",getpass.getuser(),self.impl_name()]
                if self.title : outfilenamebits.append(self.title)
                outfilenamebits.extend([time.strftime("%Y-%m-%dT%H%M%SZ",time.gmtime())])
                outfilename = "-".join(outfilenamebits)+".html"
                with open(os.path.join(self.reportdir,outfilename),"w") as outfile:
                    outfile.write(simplerenderer.render(outer.read(),{"body":pystache.render(template.read(),report)}))

        if not self.noindex: self.index_reports()

    def index_reports(self):
        import pystache

        # Get a list of all non-index html files in the reportdir
        filenames = filter(lambda x:x!="index.html",filter(lambda x:x.endswith(".html"),os.listdir(self.reportdir)))
        filenames.sort()
        filenames = map(lambda x:{"linkname":os.path.basename(x),"filename":urllib.quote(os.path.basename(x))},filenames)
        simplerenderer = pystache.Renderer(escape = lambda u: u)
        with open(os.path.join(self.templatedir,"template.tmpl"),"r") as outer:
            with open(os.path.join(self.templatedir,"index.tmpl"),"r") as template:
                with open(os.path.join(self.reportdir,"index.html"),"w") as outfile:
                    outfile.write(simplerenderer.render(outer.read(),{"body":pystache.render(template.read(),{"testlist":filenames})}))

class Interpreter(object):
    """Base class for Interpreter calling methods"""
    pass_code = 0
    fail_code = 1
    path = ""
    version = "Version unknown"
    arg_name = "generic"

    PASS = 0
    FAIL = 1
    ABORT = 2

    @classmethod
    def Construct(cls, name, *args):
        for subcls in Interpreter.__subclasses__():
            if name.lower() == subcls.__name__.lower():
                return subcls(*args)
        return cls(*args)

    @classmethod
    def Types(cls):
        interps = map(lambda c: c.__name__.lower(), Interpreter.__subclasses__())
        interps.append("generic")
        return interps

    def get_name(self):
        return os.path.basename(self.path)

    def get_version(self):
        return self.version

    def set_version(self, version=""):
        if version:
            self.version = version
        else:
            self.version = self.determine_version()

    def determine_version(self):
        if self.path:
            # Requires Python 2.7
            output = subprocess.check_output([self.path, "--version"])
            return output.strip()
        else:
            return "Unknown version"

    def set_path(self, path):
        if path:
            self.path = path

    def setup(self):
        pass

    def build_args(self, testcase):
        return [self.path, testcase.get_realpath()]

    def run_test(self, testcase):
        """Mutates testcase with appropriate result"""
        self.setup()
        command = self.build_args(testcase)

        testcase.start_timer()
        test_pipe = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output,errors = test_pipe.communicate()
        testcase.stop_timer()

        output = output.decode("utf8").encode("ascii","xmlcharrefreplace")
        errors = errors.decode("utf8").encode("ascii","xmlcharrefreplace")
        ret = test_pipe.returncode
        result = self.determine_result(testcase,ret,output,errors)
        self.teardown()

        testcase.set_result(result, ret, output, errors)

    def determine_result(self,testcase,ret,out,err):
        """Returns TestCase.{PASS,FAIL,ABORT} to indicate how the interpreter responded"""
        if ret == self.pass_code:
            return Interpreter.PASS
        elif ret == self.fail_code:
            return Interpreter.FAIL
        else:
            return Interpreter.ABORT

    def teardown(self):
        pass

class Spidermonkey(Interpreter):
    fail_code = 3
    arg_name = "spidermonkey"

    def get_name(self):
        return "SpiderMonkey"

class NodeJS(Interpreter):
    path = "/usr/bin/nodejs"
    arg_name = "node"

    def get_name(self):
        return "node.js"

class LambdaS5(Interpreter):
    current_dir = ""
    arg_name = "lambdas5"

    def get_name(self):
        return "LambdaS5"

    def set_path(self, path):
        self.path = os.path.abspath(path)

    def setup(self):
        # TODO: Use cwd parameter of Popen instead of chdir-ing??
        self.current_dir = os.getcwd()
        os.chdir(os.path.dirname(self.path))

    def teardown(self):
        os.chdir(self.current_dir)

class JSRef(Interpreter):
    interp_dir = os.path.join(JSCERT_ROOT_DIR, "interp")
    path = os.path.join(interp_dir, "run_js")
    arg_name = "jsref"
    no_parasite = False
    jsonparser = False

    def __init__(self, no_parasite=False, jsonparser=False):
        self.no_parasite = no_parasite
        self.jsonparser = jsonparser

    def get_name(self):
        return "JSRef"

    # TODO: Swap to standard once parser has a version flag
    def determine_version(self):
        out = subprocess.check_output(["git","rev-parse","HEAD"], cwd=JSCERT_ROOT_DIR)
        return out.strip()

    def build_args(self, testcase):
        # Normally we run a test like this:
        #./interp/run_js -jsparser interp/parser/lib/js_parser.jar -test_prelude interp/test_prelude.js -file filename
        # But if this is a LambdaS5 test, we need additional kit, like this:
        # ./interp/run_js -jsparser interp/parser/lib/js_parser.jar -test_prelude interp/test_prelude.js -test_prelude tests/LambdaS5/lambda-pre.js -test_prelude filename -file tests/LambdaS5/lambda-post.js
        # We can tell if it's a LambdaS5 test, because those start with "tests/LambdaS5/unit-tests/".
        # In addition, we may want to add some debug flags.
        arglist = [self.path,
                   "-jsparser",
                   os.path.join(self.interp_dir,"parser","lib","js_parser.jar")]
        if self.jsonparser:
            arglist.append("-json")
        if DEBUG:
            arglist.append("-print-heap")
            arglist.append("-verbose")
            arglist.append("-skip-init")
        arglist.append("-test_prelude")
        arglist.append(os.path.join("interp","test_prelude.js"))
        if testcase.isLambdaS5Test():
            arglist.append("-test_prelude")
            arglist.append("tests/LambdaS5/lambda-pre.js")
            arglist.append("-test_prelude")
            arglist.append(testcase.get_realpath())
            arglist.append("-file")
            arglist.append("tests/LambdaS5/lambda-post.js")
        elif testcase.isSpiderMonkeyTest():
            arglist.append("-test_prelude")
            arglist.append("interp/test_prelude_SpiderMonkey.js")
            arglist.append("-test_prelude")
            arglist.append("tests/SpiderMonkey/tests/shell.js")
            arglist.append("-file")
            arglist.append(testcase.get_realpath())
        elif testcase.usesInclude():
            if VERBOSE or DEBUG:
                print "Using include libs."
            arglist.append("-test_prelude")
            arglist.append("interp/libloader.js")
            arglist.append("-file")
            arglist.append(testcase.get_realpath())
        else:
            arglist.append("-file")
            arglist.append(testcase.get_realpath())
        if self.no_parasite:
            arglist.append("-no-parasite")
        return arglist

class Job(DBObject):
    """Information about a particular test job"""
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
        out = subprocess.check_output(["git","rev-parse","HEAD"], cwd=JSCERT_ROOT_DIR)
        self.repo_version = out.strip()

    def new_batch(self):
        self.batches.append(TestBatch(self))

    def get_batches(self):
        return self.batches

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


class TestBatch(Timer, DBObject):
    """Information about a particular test batch"""
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
        for tc in tcs:
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
        (self.system, self.osnodename, self.osrelease, self.osversion, self.hardware) = os.uname()

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
                "aborts": map(lambda x:x.report_dict() , self.aborted_tests),
                "failures": map(lambda x:x.report_dict() , self.failed_tests),
                "passes": map(lambda x:x.report_dict() , self.passed_tests)}

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

class Runtests:
    """Main class"""

    handlers = None
    db = None

    interrupted = False

    def __init__(self,):
        self.handlers = []

    def add_handler(self, handler):
        if not isinstance(handler, TestResultHandler):
            raise TypeError("%s is not a TestResultHandler" % (handler,))
        self.handlers.append(handler)

    def get_testcases_from_paths(self, paths, testcases=[], factory=TestCase):
        return reduce(
            lambda ts, p: self.get_testcases_from_path(p, ts, factory),
            paths, [])

    def get_testcases_from_path(self, path, testcases=[], factory=TestCase):
        if not os.path.exists(path):
            raise IOError("No such file or directory: %s" % path)

        if os.path.isdir(path):
            return self.get_testcases_from_dir(path, testcases, factory)
        else:
            testcases.append(factory(path))
            return testcases

    def get_testcases_from_dir(self, dirname, testcases=[], factory=TestCase):
        """Recusively walk the given directory looking for .js files, does not traverse symbolic links"""
        dirname = os.path.realpath(dirname)
        for r,d,f in os.walk(dirname):
            for filename in f:
                filename = os.path.join(r,filename)
                if os.path.isfile(filename) and filename.endswith(".js"):
                    testcases.append(factory(filename))
        return testcases

    def run(self, batch):
        batch.set_machine_details()
        batch.start_timer()

        for handler in self.handlers:
            handler.start_batch(batch)

        # Now let's get down to the business of running the tests
        while batch.has_testcase():
            testcase = batch.get_testcase()
            for handler in self.handlers:
                handler.start_test(testcase)

            batch.job.interpreter.run_test(testcase)

            batch.test_finished(testcase)

            # Inform handlers of a test result
            # We share the same TestResult among handlers
            for handler in self.handlers:
                handler.finish_test(testcase)

        batch.stop_timer()

        # Tell handlers that we're done
        for handler in self.handlers:
            handler.finish_batch(batch)

    def condor_test_import(self):
        try:
            import htcondor
            import classad
        except ImportError as e:
            print """
Could not load modules required for Condor submit support:
%s

On Imperial machines you will need to set the following environment variables to enable Condor Python support:
  export LD_LIBRARY_PATH=/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH:/vol/condor/releases/8.0.6/condor-8.0.6-x86_64_Ubuntu12-stripped/lib:/vol/condor/releases/8.0.6/condor-8.0.6-x86_64_Ubuntu12-stripped/lib/condor
  export PYTHONPATH=/vol/condor/releases/8.0.6/condor-8.0.6-x86_64_Ubuntu12-stripped/lib/python:$PYTHONPATH

(This is to workaround a broken site-wide Condor installation)""" % e
            exit(1)

    def condor_submit(self, job, machine_reqs, initial_args):
        import htcondor
        import classad

        batches = job.get_batches()
        n = len(batches)

        batch_ids = map(lambda b: b._dbid, batches)
        batch_tcs = map(lambda b: b.get_testcases(), batches)
        tc_paths = map(lambda tcs: " ".join(map(lambda t: t.get_relpath(), tcs)), batch_tcs)
        tc_ids = map(lambda tcs: ",".join(map(lambda t: str(t._dbid), tcs)), batch_tcs)

        # Fetch the name of this machine in the condor cluster
        coll = htcondor.Collector()
        machine = coll.locate(htcondor.DaemonTypes.Startd)['Machine']
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
        c['Requirements'] = machine_reqs
        c['Cmd'] = __file__
        c['Iwd'] = os.getcwd()

        if args.verbose:
            #c['Out'] = "condor_$$([ClusterId])-$$([ProcId]).out"
            c['Err'] = "condor_logs/condor_$$([ClusterId])-$$([ProcId]).err"
            #c['UserLog'] = "condor_$$([ClusterId]).log"

        # Build argument string
        args_to_copy = ["db", "dbpath", "db_pg_schema", "interp", "interp_path",
                        "interp_version", "no_parasite", "debug", "verbose"]

        arguments = ["--condor_run"]
        initial_args = vars(initial_args)
        for (arg, val) in initial_args.iteritems():
            if val and arg in args_to_copy:
                arguments.append("--%s" % arg)
                if not isinstance(val, bool):
                    arguments.append(str(val))
        arguments.append("$$([tests[ProcId]])")

        argstr =  ' '.join(arguments)
        c['Arguments'] = argstr
        if args.verbose:
            print "Using argstr: %s" % argstr

        # Build the environment
        env = dict(os.environ)
        env['_RUNTESTS_PROCID'] = "$$([ProcId])"
        env['_RUNTESTS_JOBID'] = job._dbid
        env['_RUNTESTS_BATCHID'] = "$$([batchids[ProcId]])"
        env['_RUNTESTS_TESTIDS'] = "$$([testids[ProcId]])"
        env['BISECT_FILE'] = "bisect_$$([ClusterId])-$$([ProcId])-"
        c['Environment'] = " ".join(map(lambda it: "%s='%s'" % it, env.iteritems()))

        sched = htcondor.Schedd()
        cluster_id = sched.submit(c, n)

        job.condor_scheduler = coll.locate(htcondor.DaemonTypes.Schedd)['Machine']
        job.condor_cluster = cluster_id

        return n

    def condor_run_diags(self):
        print "Argv: %s" % sys.argv
        print "Cwd: %s" % os.getcwd()
        print "Env: %s" % os.environ

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

    def interrupt_handler(self,signal,frame):
        if self.interrupted:
            print "Terminating, please be patient..."
            return

        print "Interrupted... Running pending output actions"
        self.interrupted = True

        for handler in self.handlers:
            handler.interrupt_handler(signal,frame)
        exit(1)

    def build_arg_parser(self):
        # Our command-line interface
        argp = argparse.ArgumentParser(
            description="Run some Test262-style tests with some JS implementation: by default, with JSRef.")

        argp.add_argument("filenames", metavar="path", nargs="+",
            help="The test file or directory we want to run. Directory names will recusively run all .js files.")

        argp.add_argument("--title", action="store", metavar="string", default="",
            help="Optional title for this test. Will be used in the report filename, so no spaces please!")

        argp.add_argument("--note", action="store", metavar="string", default="",
            help="Optional explanatory note to be added to the test report.")

        interp_grp = argp.add_argument_group(title="Interpreter options")
        jsr = JSRef()
        interp_grp.add_argument("--interp", action="store", choices=Interpreter.Types(), default="jsref",
            help="Interpreter type (default: jsref)")

        interp_grp.add_argument("--interp_path", action="store", metavar="path", default="",
            help="Where to find the interpreter (a sensible default may be provided for some types)")

        interp_grp.add_argument("--interp_version", action="store", metavar="version", default="",
            help="The version of the interpreter you're running. (Default is type-specific, usually by executing the --version flag of the interpeter)")

        interp_grp.add_argument("--jsonparser", action="store_true",
            help="Use the JSON parser (Esprima) when running tests.")

        interp_grp.add_argument("--no_parasite",action="store_true",
            help="Run JSRef with -no-parasite flag (the options --debug and --verbose might be useless in this mode).")

        interp_grp.add_argument("--debug",action="store_true",
            help="Run JSRef with debugging flags (-print-heap -verbose -skip-init).")

        report_grp = argp.add_argument_group(title="Report Options")
        report_grp.add_argument("--webreport",action="store_true",
            help="Produce a web-page of your results in the default web directory. Requires pystache.")

        report_grp.add_argument("--templatedir",action="store",metavar="path", default=os.path.join("test_reports"),
            help="Where to find our web-templates when producing reports")

        report_grp.add_argument("--reportdir",action="store",metavar="path",default=os.path.join("test_reports"),
            help="Where to put our test reports")

        report_grp.add_argument("--noindex",action="store_true",
            help="Don't attempt to build an index.html for the reportdir")

        argp.add_argument("--verbose",action="store_true",
            help="Print the output of the tests as they happen.")


        # Database config
        db_args = argp.add_argument_group(title="Database options")
        db_args.add_argument("--db", action="store", choices=['sqlite', 'postgres'],
            help="Save the results of this testrun to the database")

        db_args.add_argument("--dbpath", action="store", metavar="file", default="",
            help="Path to the database (for SQLite) or configuration file (for Postgres).")

        db_args.add_argument("--db_init", action="store_true",
            help="Create the database and load schema")

        db_args.add_argument("--db_pg_schema", action="store", metavar="name", default="jscert",
            help="Schema of Postgres database to use. (Defaults to 'jscert')")


        # Condor infos
        condor_args = argp.add_argument_group(title="Condor Options")
        condor_args.add_argument("--condor", action="store_true",
            help="Schedule these testcases on the Condor distributed computing cluster, requires --psqlconfig")

        condor_args.add_argument("--condor_req", action="store", metavar="reqs", default="OpSysMajorVersion > 12",
            help="ClassAd describing minimum requirements for machines jobs are to run on, defaults to ICDoC minimum")

        condor_args.add_argument("--batch_size", action="store", metavar="n", default=-1, type=int,
            help="Number of testcases to run per Condor batch, if 0 run all tests in a single batch, otherwise run n tests per batch.")

        condor_args.add_argument("--condor_run", action="store_true", help=argparse.SUPPRESS)

        return argp

    def main(self):
        argp = self.build_arg_parser()
        args = argp.parse_args()

        global VERBOSE
        global DEBUG
        VERBOSE = args.verbose
        DEBUG = args.debug

        if args.condor:
            self.condor_test_import()

        if args.condor_run and args.verbose:
            self.condor_run_diags()

        if args.db:
            if args.db == "sqlite":
                if args.condor:
                    raise Exception("Only PostgresSQL may be used in a condor environment")

                if not args.dbpath:
                    args.dbpath = os.path.join(JSCERT_ROOT_DIR, "test_data", "test_results.db")

                dbmanager = SQLiteDBManager(args.dbpath, args.db_init)

            elif args.db == "postgres":
                if not args.dbpath:
                    args.dbpath = os.path.join(JSCERT_ROOT_DIR, ".pgconfig")
                try:
                    with open(args.dbpath, "r") as f:
                        dbmanager = PostgresDBManager(f.readline(), args.db_pg_schema)
                except IOError as e:
                    raise Exception("Could not open postgres configuration: %s" % e)

            if args.db_init:
                dbmanager.connect()
                dbmanager.import_schema()
                print "Database created successfully"
                exit(0)

            self.add_handler(dbmanager)
        else:
            dbmanager = None

        # Interpreter
        interpreter = Interpreter.Construct(args.interp)
        if isinstance(interpreter, JSRef):
            interpreter.no_parasite = args.no_parasite
            interpreter.jsonparser = args.jsonparser
        interpreter.set_path(args.interp_path)
        interpreter.set_version(args.interp_version)

        # Generate testcases
        testcases = self.get_testcases_from_paths(args.filenames)
        if dbmanager and not args.condor_run:
            print "Preloading test-cases into database...",
            dbmanager.connect()
            dbmanager.insert_testcases(testcases) # auto-commits
            print " Done!"

        # Build job
        job = Job(args.title, args.note, interpreter)

        if args.batch_size < 0:
            if args.condor:
                job.batch_size = 1
            else:
                job.batch_size = 0
        else:
            job.batch_size = args.batch_size

        job.add_testcases(testcases)

        # Insert it all into the database
        if not args.condor_run:
            if dbmanager:
                dbmanager.create_job_batches_runs(job)

        # Submit job to Condor?
        if args.condor:
            n = self.condor_submit(job, args.condor_req, args)
            dbmanager.update_object(job)
            dbmanager.disconnect()
            print ("Submitted %s jobs to cluster %s on %s. Test job id: %s" %
                (n, job.condor_cluster, job.condor_scheduler, job._dbid))
            exit(0)

        # What other output handlers do we want to configure?
        self.add_handler(CLIResultPrinter(args.verbose or args.debug))
        if args.webreport:
            self.add_handler(WebResultPrinter(args.templatedir, args.reportdir, args.noindex))
        # What to do if the user hits control-C
        signal.signal(signal.SIGINT, self.interrupt_handler)

        # Pick the batch to run
        batch = None
        if args.condor_run:
            dbmanager.wait_for_batch = True
            batch = self.condor_update_job(job, dbmanager)
        else:
            batch = job.batches[0]

        # Let's go!
        self.run(batch)

if __name__ == "__main__":
    Runtests().main()
