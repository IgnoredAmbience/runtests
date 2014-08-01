#!/usr/bin/env python
"""
A mini test harness. Runs all the files you specify through an interpreter
you specify, and collates the exit codes for you. Call with the -h switch to
find out about options.
"""

import argparse
import signal
import subprocess
import os
import getpass
import sqlite3 as db
import psycopg2
import datetime
import re
import urllib
from collections import dequeue
import pwd

JSCERT_ROOT_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), ".."))
DEBUG=False
VERBOSE=False

# Some handy data structures

class Timer:
    start_time = None
    stop_time = None

    def start_timer(self):
        self.start_time = datetime.now()

    def stop_timer(self):
        self.stop_time = datetime.now()

    def get_delta(self):
        return self.stop_time - self.start_time

    def get_duration(self):
        return self.get_delta().total_seconds()

class TestCase(Timer):
    """
    A test case knows what file it came from, whether it has been run and if so,
    whether it passed, failed or aborted, and what output it generated along the way.
    """
    _table = "test_runs"
    _dbid = 0

    # Fake-enum for result
    UNKNOWN = 0
    PASS = 1
    FAIL = 2
    ABORT = 3
    RESULT_TEXT = ["UNKNOWN","PASS","FAIL","ABORT"]

    testname = ""
    filename = ""      # absolute path
    negative = False   # Whether the testcase is expected to fail
    includes = None    # List of required JS helper files for test to run

    # Test results
    result = UNKNOWN   # Derived from exit_code by an interpreter class
    exit_code = -1     # UNIX exit code
    stdout = ""
    stderr = ""

    def __init__(self,filename,result,stdout,stderr):
        self.filename = os.path.abspath(filename)
        self.testname = os.path.basename(self.filename)

    def fetch_file_info(self):
        if self.includes == None:
            with open(self.filename) as f:
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
        return os.path.relpath(self.filename, JSCERT_ROOT_DIR)

    def report_dict(self):
        return {"testname": self.testname,
                "filename": self.filename,
                "stdout": self.stdout,
                "stderr": self.stderr}

    def db_dict(self):
        return {"id": self._dbid,
                "test_id": self.get_relpath(),
                "result": self.get_result_text(),
                "exit_code": self.exit_code,
                "stdout": self.stdout,
                "stderr": self.stderr,
                "duration": self.get_duation()}

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

class TestResultHandler:
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
    con = None

    def connect(self):
        """Only implement for db backends with limited connection pools"""
        pass

    def disconnect(self):
        """Only implement for db backends with limited connection pools"""
        pass

    def insert_testcases(self, cur, testcases):
        tcds = map(lambda t: t.db_tc_dict(), testcases)
        self.insert_ignore_many(cur, TestCase._table, tcds)

    def create_job(self, cur, job):
        self.insert_object(cur, job)

    def create_batch(self, cur, batch):
        self.insert_object(cur, batch)

    def start_batch(self, batch):
        with self.conn.cursor() as cur:
            self.update_object(cur, batch)
        self.commit()
        self.disconnect()

    def finish_batch(self, batch):
        self.connect()
        with self.conn.cursor() as cur:
            self.update_object(cur, batch)
            self.update_objects(cur, batch.get_finished_testcases())
        self.commit()

    # Helper functions
    def build_fields(self, fields):
        """
        Builds a field list pattern to substitute into a SQL statement, eg:
        ["a","b","c"] ==> [ "a,b,c", ":a,:b,:c" ]
        """
        key_pairs = map(lambda k: (k, self.subst_pattern(k)), fields)
        key_lists = zip(key_pairs)
        return map(",".join, key_lists)

    def insert(self, cur, table, dic):
        """Retrieval of inserted id is implementation-specific"""
        raise NotImplementedError

    def insert_many(self, cur, table, coll):
        (fnames, fsubst) = build_fields(coll[0].keys())
        sql = ("INSERT INTO %s (%s) VALUES (%s)" % (table, fnames, fsubst))
        cur.executemany(sql, coll)

    def insert_ignore_many(self, cur, table, dic):
        """Insert or ignore row with colliding ID and commits"""
        raise NotImplementedError

    def insert_object(self, cur, obj):
        if not obj._table:
            raise Exception("Object not suitable for database insertion")
        else:
            obj._dbid = self.insert(cur, obj._table, obj.db_dict())

    def update(self, cur, table, dic):
        if "id" not in dic:
            raise Exception("Needs id field")
        self.update_many(cur, table, [dic])

    def update_many(self, cur, table, coll):
        """Expects dbid to be set on all dicts being passed in for updating"""
        (fnames, fsubst) = build_fields(coll[0].keys())
        sql = ("UPDATE %s SET (%s) = (%s) WHERE id = %s" % (table, fnames, fsubst, self.subst_pattern("id")))
        cur.executemany(sql, coll)

    def update_object(self, cur, obj):
        if not obj._table:
            raise Exception("Object not suitable for database insertion")
        else:
            self.update(cur, obj._table, obj.db_dict())

    def update_objects(self, cur, objs):
        """Assumes all objects passed in are of same class"""
        table = objs[0]._table
        dicts = map(lambda o: o.db_dict(), objs)
        self.update_many(self, cur, table, dicts)

class SQLiteDBManager(DBManager):
    def __init__(self):
        if not os.path.isfile(args.dbpath):
            print args.dbpath
            print """ You need to set up your personal results database before saving data to it.
            See the README for details. """
            exit(1)
        self.con = db.connect(args.dbpath)

    def subst_pattern(self, field):
        return (":%s" % field)

    def insert(self, cur, table, dic):
        (fnames, fsubst) = build_fields(dic.keys())
        sql = ("INSERT INTO %s (%s) VALUES (%s)" % (table, fnames, fsubst))
        cur.execute(sql, dic)
        return cur.lastrowid

    def insert_ignore_many(self, cur, table, coll):
        """Insert or ignore rows with colliding ID and commits"""
        (fnames, fsubst) = build_fields(coll[0].keys())
        sql = ("INSERT OR IGNORE INTO %s (%s) VALUES (%s)" % (table, fnames, fsubst))
        cur.executemany(sql, dic)
        self.conn.commit()

class PostgresDBManager(DBManager):
    connstr = ""
    schema = ""

    def __init__(self, connstr, schema="jscert"):
        self.connstr = connstr
        self.schema = schema

    def connect(self):
        if not self.conn or self.conn.closed:
            self.conn = pyscopg2.connect(self.connstr)
            with self.conn.cursor() as cur:
                cur.execute("SET SCHEMA %s", self.schema)
            self.conn.commit()

    def disconnect(self):
        self.conn.close()

    def subst_pattern(self, field):
        return ("%%(%s)" % field)

    def insert(self, cur, table, dic):
        (fnames, fsubst) = build_fields(dic.keys())
        sql = ("INSERT INTO %s (%s) VALUES (%s) RETURNING id" % (table, fnames, fsubst))
        cur.execute(sql, dic)
        return cur.fetchone()[0]

    def insert_ignore_many(self, cur, table, coll):
        """Insert or ignore rows with colliding ID, and commits"""
        (fnames, fsubst) = build_fields[0].keys())
        sql = ("INSERT INTO %s (%s) SELECT %s WHERE NOT EXISTS (SELECT 1 FROM %s WHERE id = %s)" %
               (table, fnames, fsubst, table, self.subst_pattern("id")))

        cur.execute("LOCK TABLE mailing_list IN SHARE ROW EXCLUSIVE MODE")
        cur.executemany(sql, coll)
        self.conn.commit()

class CLIResultPrinter(TestResultHandler):
    # Some pretty colours for our output messages.
    NORMAL = "\033[00m"
    HEADING = "\033[35m"
    PASS = "\033[32m"
    FAIL = "\033[31m"
    ABANDON = "\033[33m"

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
        if VERBOSE or DEBUG:
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

class Interpreter:
    """Base class for Interpreter calling methods"""
    pass_code = 0
    fail_code = 1
    path = ""
    version = "Version unknown"

    PASS = 0
    FAIL = 1
    ABORT = 2

    def __init__(self):
        self.set_version()

    def get_name(self):
        return os.path.basename(self.path)

    def set_version(self):
        if self.path:
            # Requires Python 2.7
            output = subprocess.check_output([self.path, "--version"])
            self.version = output.strip()

    # Intereter "lifecycle" follows
    def set_path(self,path):
        if path:
            self.path = path

    def setup(self):
        pass

    def build_args(self, testcase):
        return [self.path, testcase.filename]

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

    def get_name(self):
        return "SpiderMonkey"

class NodeJS(Interpreter):
    path = "/usr/bin/nodejs"

    def get_name(self):
        return "node.js"

class LambdaS5(Interpreter):
    current_dir = ""

    def get_name(self):
        return "LambdaS5"

    def setup(self):
        # TODO: Use cwd parameter of Popen instead of chdir-ing??
        self.current_dir = os.getcwd()
        os.chdir(os.path.dirname(self.path))

    def build_args(self,filename):
        return [os.path.abspath(self.path), filename]

    def teardown(self):
        os.chdir(self.current_dir)

class JSRef(Interpreter):
    interp_dir = os.path.join(JSCERT_ROOT_DIR,"interp")
    path = os.path.join(interp_dir,"run_js")
    jsonparser = False
    no_parasite = False

    def __init__(self, no_parasite=False, jsonparser=False):
        self.no_parasite = no_parasite
        self.jsonparser = jsonparser

    def get_name(self):
        return "JSRef"

    # TODO: Swap to standard once parser has a version flag
    def set_version(self):
        out = subprocess.check_output(["git","rev-parse","HEAD"])
        self.version = out.strip()

    def build_args(self,filename):
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
        if filename.startswith(os.path.join(os.getcwd(),"tests/LambdaS5/unit-tests/")):
            arglist.append("-test_prelude")
            arglist.append("tests/LambdaS5/lambda-pre.js")
            arglist.append("-test_prelude")
            arglist.append(filename)
            arglist.append("-file")
            arglist.append("tests/LambdaS5/lambda-post.js")
        elif filename.startswith(os.path.join(os.getcwd(), "tests/SpiderMonkey/")):
            arglist.append("-test_prelude")
            arglist.append("interp/test_prelude_SpiderMonkey.js")
            arglist.append("-test_prelude")
            arglist.append("tests/SpiderMonkey/tests/shell.js")
            arglist.append("-file")
            arglist.append(filename)
        elif self.usesInclude(filename):
            if VERBOSE or DEBUG:
                print "Using include libs."
            arglist.append("-test_prelude")
            arglist.append("interp/libloader.js")
            arglist.append("-file")
            arglist.append(filename)
        else:
            arglist.append("-file")
            arglist.append(filename)
        if self.no_parasite:
            arglist.append("-no-parasite")
        return arglist

class Job:
    """Information about a particular test job"""
    _table = "test_jobs"
    _dbid = 0
    title = ""
    note = ""
    impl_name = ""
    impl_version = ""
    repo_version = ""
    create_time = None
    user = ""

    condor_cluster = 0

    def __init__(self):
        self.create_time = datetime.now()
        self.set_repo_version()
        self.user = pwd.getpwuid(os.geteuid()).pw_name

    def set_repo_version(self):
        out = subprocess.check_output(["git","rev-parse","HEAD"])
        self.repo_version = out.strip()

    def db_dict(self):
        return {"id": self._dbid,
                "title": self.title,
                "note": self.note,
                "impl_name": self.impl_name,
                "impl_version": self.impl_version,
                "create_time": self.create_time,
                "repo_version": self.repo_version,
                "username": self.user,
                "condor_cluster": self.condor_cluster}


class TestBatch(Timer):
    """Information about a particular test batch"""
    _table = "test_batches"
    _dbid = 0
    job = None

    # Machine info
    system = ""
    osnodename = ""
    osrelease = ""
    osversion = ""
    hardware = ""

    condor_proc = 0

    pending_tests = None

    # Classified test cases
    passed_tests = None
    failed_tests = None
    aborted_tests = None

    def __init__(self, job):
        (sysname, nodename, release, version, machine) = os.uname()
        self.pending_tests = dequeue()
        self.passed_tests = []
        self.failed_tests = []
        self.aborted_tests = []

    def add_testcase(self, testcase):
        self.pending_tests.append(testcase)

    def has_testcase(self):
        return len(self.pending_tests) > 0

    def get_testcase(self):
        return self.pending_tests.popleft()

    def get_finished_testcases(self):
        return self.passed_tests + self.failed_tests + self.aborted_tests

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

    def db_dict(self):
        d = {"id": self._dbid,
             "system": self.system,
             "osnodename": self.osnodename,
             "osrelease": self.osrelease,
             "osversion": self.osversion,
             "hardware": self.hardware,
             "start_time": self.start_time,
             "end_time": self.end_time,
             "condor_proc": self.condor_proc}
        if self.job != None:
            d['job_id'] = self.job._dbid
        return d

class Runtests:
    """Main class"""

    interpreter = None
    handlers = None

    interrupted = False

    def __init__(self,interpreter):
        self.handlers = []
        self.interpreter = interpreter

    def add_path(self,path):
        # Sanitise pathname
        path = os.path.realpath(path)

        if not os.path.exists(path):
            raise IOError("No such file or directory: %s" % path)

        if os.path.isdir(path):
            self.add_dir(path)
        else:
            self.add_file(path)

    def add_file(self,filename):
        self.filenames.append(filename)

    def add_dir(self,dirname):
        for r,d,f in os.walk("."):
            for filename in f:
                filename = os.path.join(r,filename)
                if os.path.isfile(filename) and filename.endswith(".js"):
                    self.add_file(filename)

    def add_result_handler(self,handler):
        self.handlers.append(handler)

    def run(self, batch):
        # Now let's get down to the business of running the tests
        for handler in self.handlers:
            handler.start_batch(batch)

        batch.start_timer()

        while batch.has_testcase():
            testcase = batch.get_testcase()
            for handler in self.handlers:
                handler.start_test(testcase)

            self.interpreter.run_test(testcase)

            batch.test_finished(testcase)

            # Inform handlers of a test result
            # We share the same TestResult among handlers
            for handler in self.handlers:
                handler.finish_test(testcase)

        batch.stop_timer()

        # Tell handlers that we're done
        for handler in self.handlers:
            handler.end_batch(batch)

    def interrupt_handler(self,signal,frame):
        if self.interrupted:
            print "Terminating, please be patient..."
            return

        print "Interrupted... Running pending output actions"
        self.interrupted = True

        for handler in self.handlers:
            handler.interrupt_handler(signal,frame)
        exit(1)

def main():
    # Our command-line interface
    argp = argparse.ArgumentParser(
        description="Run some Test262-style tests with some JS implementation: by default, with JSRef.")

    argp.add_argument("filenames", metavar="path", nargs="+",
        help="The test file or directory we want to run. Directory names will recusively run all .js files.")

    argp.add_argument("--interp_path", action="store", metavar="path", default="",
        help="Where to find the interpreter.")

    argp.add_argument("--interp_version", action="store", metavar="version", default="",
        help="The version of the interpreter you're running. Default is the git hash of the current directory.")

    argp.add_argument("--jsonparser", action="store_true",
        help="Use the JSON parser (Esprima) when running tests.")

    engines_grp = argp.add_argument_group(title="Alternative JS Engine Selection",description="All of these options probably should also have --interp_path set. Some some system defaults may be attempted.")
    engines_ex_grp = engines_grp.add_mutually_exclusive_group()
    engines_ex_grp.add_argument("--spidermonkey", action="store", dest="interpreter", const=Spidermonkey(),
        help="Test SpiderMonkey instead of JSRef. If you use this, you should probably also use --interp_path")

    engines_ex_grp.add_argument("--lambdaS5", action="store", dest="interpreter", const=LambdaS5(),
        help="Test LambdaS5 instead of JSRef. If you use this, you should probably also use --interp_path")

    engines_ex_grp.add_argument("--nodejs", action="store", dest="interpreter", const=NodeJS(),
        help="Test node.js instead of JSRef. If you use this, you should probably also use --interp_path")

    report_grp = argp.add_argument_group(title="Report Options")
    report_grp.add_argument("--webreport",action="store_true",
        help="Produce a web-page of your results in the default web directory. Requires pystache.")

    report_grp.add_argument("--templatedir",action="store",metavar="path", default=os.path.join("test_reports"),
        help="Where to find our web-templates when producing reports")

    report_grp.add_argument("--reportdir",action="store",metavar="path",default=os.path.join("test_reports"),
        help="Where to put our test reports")

    report_grp.add_argument("--title",action="store",metavar="string", default="",
        help="Optional title for this test. Will be used in the report filename, so no spaces please!")

    report_grp.add_argument("--note",action="store",metavar="string", default="",
        help="Optional explanatory note to be added to the test report.")

    report_grp.add_argument("--noindex",action="store_true",
        help="Don't attempt to build an index.html for the reportdir")

    argp.add_argument("--verbose",action="store_true",
        help="Print the output of the tests as they happen.")

    argp.add_argument("--debug",action="store_true",
        help="Run the interpreter with debugging flags (-print-heap -verbose -skip-init).")

    argp.add_argument("--no_parasite",action="store_true",
        help="Run the interpreter with -no-parasite flag (the options --debug and --verbose might be useless in this mode).")

    db_args = argp.add_argument_group(title="Database options")

    db_args.add_argument("--dbsave",action="store_true",
        help="Save the results of this testrun to the database")

    db_args.add_argument("--dbpath",action="store",metavar="path",
        default="test_data/test_results.db",
        help="Path to the database to save results in. The default should usually be fine. Please don't mess with this unless you know what you're doing.")

    db_args.add_argument("--psqlconfig",action="store",metavar="psqlconfig",default="",
        help="Use PostgreSQL backed database, give path to file containing libpq connection string")


    # Condor infos
    condor_args = argp.add_argument_group(title="Condor Options")
    condor_args.add_argument("--condor", action="store_true",
        help="Run these testcases on the Condor distributed computing cluster, requires --psqlconfig")

    condor_args.add_argument("--runid",action="store",metavar="runid",default=0,
        help="(Internal) Test run ID, to cross reference condor processes and cluster")

    condor_args.add_argument("--procid",action="store",metavar="condorprocid",default=0,
        help="(Internal) Process ID for crossreference with Condor logs")

    args = argp.parse_args()

    global VERBOSE
    global DEBUG
    VERBOSE = args.verbose
    DEBUG = args.debug


    exit(0)

    runtests = Runtests()

    # Tests to run
    for filename in args.filenames:
        runtests.add_path(filename)

    # Interpreter to use
    interpreter = JSRef(no_parasite=args.no_parasite, jsonparser=args.jsonparser)
    if interpreter in args:
        interpreter = args.interpreter
    interpreter.set_path(args.interp_path)
    runtests.set_interpreter(args.interpreter)

    # How to save results
    if(args.dbsave):
        dbmanager = SQLiteDBManager()
    elif(args.psqlconfig):
        dbmanager = PgDBManager()

    runtests.add_handler(CLIResultPrinter())

    if(not args.condor and args.webreport):
        runtests.add_handler(WebResultPrinter())

    # What to do if the user hits control-C
    signal.signal(signal.SIGINT, runtests.interrupt_handler)

    runtests.run()

if __name__ == "__main__":
    main()
