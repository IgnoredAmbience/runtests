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
import calendar
import sqlite3 as db
import psycopg2
import time
import re

JSCERT_ROOT_DIR = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
DEBUG=False
VERBOSE=False

# Some handy data structures

class TestCase:
    """
    A test case knows what file it came from, whether it has been run and if so,
    whether it passed, failed or aborted, and what output it generated along the way.
    """

    # Fake-enum for result
    UNKNOWN = -1
    PASS = 0
    FAIL = 1
    ABORT = 2

    testname = ""
    filename = ""      # absolute path
    has_run = False
    negative = False   # Whether the testcase is expected to fail
    includes = []      # List of required JS helper files for test to run

    # Test results
    result = UNKNOWN   # Derived from exit_code by an interpreter class
    exit_code = -1            # UNIX exit code
    stdout = ""
    stderr = ""

    def __init__(self,filename,result,stdout,stderr):
        self.filename = os.path.abspath(filename)
        self.testname = os.path.basename(self.filename)

        with open(filename) as f:
            # If this was a sputnik test, it may have expected to fail.
            # If so, we will need to invert the return value later on.
            buf = f.read()
            self.negative = "@negative" in buf
            # Taken from test262, copyright sputnik authors, BSD licenced
            self.includes = re.findall('\$INCLUDE\([\'"]([^\)]+)[\'"]\)', buf)

    def set_result(self,result,exit_code,stdout,stderr):
        self.interp_result = result
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

    def set_passed(self):
        if(self.negative):
            self.result = self.FAIL
        else:
            self.result = self.PASS

    def passed(self):
        return self.result == self.PASS

    def set_failed(self):
        if(self.negative):
            self.result = self.PASS
        else:
            self.result = self.FAIL

    def failed(self):
        return self.result == self.FAIL

    def set_aborted(self):
        self.result = self.ABORT

    def aborted(self):
        return self.result == self.ABORT

    def report_dict(self):
        return {"testname":self.testname,
                "filename":self.filename,
                "stdout":self.stdout,
                "stderr":self.stderr}

    # Does this test try to load other libraries?
    def usesInclude(self):
        return len(includes) > 0

class TestResultHandler:
    """
    Recieves notifications of events in the test cycle

    A test is the execution of an individual test file
    A test batch it is a number of sequential executions of tests
    A test job is a collection of test batches, it may only use one interpreter
    """
    def create_job(self):
        """Called once per user-invokation of the program"""
        pass

    def create_batch(self):
        """Called when a batch is scheduled for execution"""
        pass

    def start_batch(self):
        """Called before the first test is run from a particular batch"""
        pass

    def start_test(self,test):
        """Called before each test is run"""
        pass

    def finish_test(self,test):
        """Called after each test is run"""
        pass

    def finish_batch(self):
        """Called after the last test from a batch is run"""
        pass

class SQLiteDBManager(TestResultHandler):
    pass

class PgDBManager(TestResultHandler):
    pass

class DBManager:
    PASS = "PASS"
    FAIL = "FAIL"
    ABORT = "ABORT"

    INSERT_SINGLE_STMT = "insert into single_test_runs(test_id, batch_id, status, stdout, stderr) values (?,?,?,?,?)"

    con = None
    curdir = os.getcwd()

    def __init__(self):
        if not os.path.isfile(args.dbpath):
            print args.dbpath
            print """ You need to set up your personal results database before saving data to it.
            See the README for details. """
            exit(1)
        self.con = db.connect(args.dbpath)

    def makerelative(self,path):
        return re.sub("^"+self.curdir+"/","",path)

    def create_batch(self,cur,results,version):
        cur.execute("insert into test_batch_runs(time, implementation, impl_path, impl_version, title, notes, timestamp, system, osnodename, osrelease, osversion, hardware) values (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (results["timetaken"],
                     results["implementation"],
                     args.interp_path,
                     version,
                     results["testtitle"],
                     results["testnote"],
                     calendar.timegm(time.gmtime()),
                     results["system"],
                     results["osnodename"],
                     results["osrelease"],
                     results["osversion"],
                     results["hardware"]))
        cur.execute("SELECT id FROM test_batch_runs ORDER BY id DESC LIMIT 1")
        batchid = cur.fetchone()[0]
        return batchid

    def report_results(self,results):
        test_pipe = subprocess.Popen(["git","rev-parse","HEAD"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        githash,errors = test_pipe.communicate()
        version = re.sub(r'\n','',githash)
        if args.interp_version:
            version = args.interp_version
        #with self.con:
        try:
            cur = self.con.cursor()
            batchid = self.create_batch(cur, results, version)

            def insert_single(status,case):
                cur.execute(self.INSERT_SINGLE_STMT,
                            (self.makerelative(case["filename"]),
                             batchid,
                             status,
                             case["stdout"],
                             case["stderr"]))

            for case in results["aborts"]:
                # Insert abort cases
                insert_single(self.ABORT,case)
            for case in results["failures"]:
                # Insert fail cases
                insert_single(self.FAIL,case)
            for case in results["passes"]:
                # Insert pass cases
                insert_single(self.PASS,case)
            self.con.commit()
        except Exception as e:
            print "Error"
            print e
            exit(1)

# When running concurrently as a distributed system, we cannot use sqlite over nfs due to locking issues
# We additionally batch tests into an unbrella test run using the passed in runid
class PGDBManager(DBManager):
    def __init__(self):
        with open(args.psqlconfig) as f:
            psqlconfig = f.readline()

        self.con = psycopg2.connect(psqlconfig)
        self.INSERT_SINGLE_STMT = self.INSERT_SINGLE_STMT.replace("?","%s")

    def create_batch(self,cur,results,version):
        cur.execute("insert into test_batch_runs(time, implementation, impl_path, impl_version, title, notes, timestamp, system, osnodename, osrelease, osversion, hardware, run_id, condor_proc) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (results["timetaken"],
                     results["implementation"],
                     args.interp_path,
                     version,
                     results["testtitle"],
                     results["testnote"],
                     calendar.timegm(time.gmtime()),
                     results["system"],
                     results["osnodename"],
                     results["osrelease"],
                     results["osversion"],
                     results["hardware"],
                     args.runid,
                     args.procid))
        cur.execute("SELECT id FROM test_batch_runs ORDER BY id DESC LIMIT 1")
        batchid = cur.fetchone()[0]
        return batchid

class CLIResultPrinter(ResultHandler):
    # Some pretty colours for our output messages.
    NORMAL = "\033[00m"
    HEADING = "\033[35m"
    PASS = "\033[32m"
    FAIL = "\033[31m"
    ABANDON = "\033[33m"

    passed_test_count = 0
    failed_tests = None
    abandoned_tests = None

    def __init__(self):
        failed_tests = []
        abandoned_tests = []

    def start_test(self,filename):
        self.print_heading(filename)

    def finish_test(self,result):
        if result.passed():
            self.print_pass("Passed!")
            self.passed_test_count += 1
        elif result.failed():
            self.print_fail("Failed :/")
            self.failed_tests.append(result)
        elif result.aborted():
            self.print_abandon("Aborted...")
            self.aborted_tests.append(result)
        else:
            print self.ABANDON+"Something really weird happened"+self.NORMAL
        if VERBOSE or DEBUG:
            print "=== STDOUT ==="
            print result.stdout
            print "=== STDERR ==="
            print result.stderr

    def print_heading(self,s):
        print self.HEADING+s+self.NORMAL
    def print_pass(self,s):
        print self.PASS+s+self.NORMAL
    def print_fail(self,s):
        print self.FAIL+s+self.NORMAL
    def print_abandon(self,s):
        print self.ABANDON+s+self.NORMAL

    def end_message(self):
        if len(self.failed_tests) > 0:
            print "The following tests failed:"
            for failure in self.failed_tests:
                print failure.filename
        if len(self.aborted_tests) > 0:
            print "The following tests were abandoned"
            for abandoned in self.aborted_tests:
                print abandoned.filename
        print "There were %d passes, %d fails, and %d abandoned tests." % (self.passed_test_count, len(self.failed_tests), len(self.aborted_tests))

class WebResultPrinter(ResultHandler):
    """
    This class maintains the results of our test run, and generates a html report
    """

    # Which tests passed, and which failed?
    passed_tests = []
    failed_tests = []
    aborted_tests = []

    # Time the testrun
    starttime = 0
    time_taken = 0

    def start_batch(self):
        self.starttime = calendar.timegm(time.gmtime())

    def end_batch(self):
        self.time_taken = calendar.timegm(time.gmtime()) - self.starttime
        self.end_message()

    def finish_test(self,result):
        if result.passed():
            self.passed_tests.append(result)
        elif result.failed():
            self.failed_tests.append(result)
        elif result.aborted():
            self.aborted_tests.append(result)

    def make_report(self):
        (sysname, nodename, release, version, machine) = os.uname()

        return {"testtitle":args.title,
                "testnote":args.note,
                "implementation":self.impl_name(),
                "system":sysname,
                "timetaken":self.time_taken,
                "osnodename":nodename,
                "osrelease":release,
                "osversion":version,
                "hardware":machine,
                "time":time.asctime(time.gmtime()),
                "user":getpass.getuser(),
                "numpasses":len(self.passed_tests),
                "numfails":len(self.failed_tests),
                "numaborts":len(self.aborted_tests),
                "aborts":map(lambda x:x.report_dict() , self.aborted_tests),
                "failures":map(lambda x:x.report_dict() , self.failed_tests),
                "passes":map(lambda x:x.report_dict() , self.passed_tests)}

    def update_database(self):
        self.dbmanager.report_results(self.make_report())

    def impl_name(self):
        if args.spidermonkey: return "SpiderMonkey"
        if args.nodejs: return "node.js"
        if args.lambdaS5: return "LambdaS5"
        return "JSRef"


    def produce_web_page(self):
        import pystache

        report = self.make_report()

        simplerenderer = pystache.Renderer(escape = lambda u: u)
        with open(os.path.join(args.templatedir,"template.tmpl"),"r") as outer:
            with open(os.path.join(args.templatedir,"test_results.tmpl"),"r") as template:
                outfilenamebits = ["report",getpass.getuser(),self.impl_name()]
                if args.title : outfilenamebits.append(args.title)
                outfilenamebits.extend([time.strftime("%Y-%m-%dT%H%M%SZ",time.gmtime())])
                outfilename = "-".join(outfilenamebits)+".html"
                with open(os.path.join(args.reportdir,outfilename),"w") as outfile:
                    outfile.write(simplerenderer.render(outer.read(),{"body":pystache.render(template.read(),report)}))

        if not args.noindex: self.index_reports()

    def index_reports(self):
        import pystache
        import urllib
        # Get a list of all non-index html files in the reportdir
        filenames = filter(lambda x:x!="index.html",filter(lambda x:x.endswith(".html"),os.listdir(args.reportdir)))
        filenames.sort()
        filenames = map(lambda x:{"linkname":os.path.basename(x),"filename":urllib.quote(os.path.basename(x))},filenames)
        simplerenderer = pystache.Renderer(escape = lambda u: u)
        with open(os.path.join(args.templatedir,"template.tmpl"),"r") as outer:
            with open(os.path.join(args.templatedir,"index.tmpl"),"r") as template:
                with open(os.path.join(args.reportdir,"index.html"),"w") as outfile:
                    outfile.write(simplerenderer.render(outer.read(),{"body":pystache.render(template.read(),{"testlist":filenames})}))


    def end_message(self):
        if len(self.failed_tests)>0:
            print "The following tests failed:"
            for failure in self.failed_tests:
                print failure.filename
        if len(self.aborted_tests)>0:
            print "The following tests were abandoned"
            for abandoned in self.aborted_tests:
                print abandoned.filename
        print "There were "+str(len(self.passed_tests))+" passes, "+str(len(self.failed_tests))+"  fails, and "+str(len(self.aborted_tests))+" abandoned."
        if args.webreport:
            self.produce_web_page()
        if args.dbsave:
            self.update_database()

    def interrupt_handler(self,signal,frame):
        print "Interrupted..."
        self.end_message()
        exit(1)

class Interpreter:
    """Base class for Interpreter calling methods"""
    PASS_CODE = 0
    FAIL_CODE = 1
    path = ""

    def set_path(self,path):
        if path:
            self.path = path

    def setup(self):
        pass

    def build_args(self,testcase):
        return [path, testcase.filename]

    def run_test(self,testcase):
        """Mutates testcase with appropriate result"""
        self.setup()
        command = self.build_args(testcase)
        test_pipe = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output,errors = test_pipe.communicate()

        output = output.decode("utf8").encode("ascii","xmlcharrefreplace")
        errors = errors.decode("utf8").encode("ascii","xmlcharrefreplace")
        ret = test_pipe.returncode
        self.determine_result(testcase,ret,output,errors)
        self.teardown()

        test_result = testcase.set_result(result,ret,output,errors)

    def determine_result(self,testcase,ret,out,err):
        """Returns TestCase.{PASS,FAIL,ABORT} to indicate how the interpreter responded"""
        if(ret == self.PASS_CODE):
            testcase.set_passed()
        elif(ret == self.FAIL_CODE):
            testcase.set_failed()
        else:
            testcase.set_aborted()

    def teardown(self):
        pass

class Spidermonkey(Interpreter):
    FAIL_CODE = 3

class NodeJS(Interpreter):
    pass

class LambdaS5(Interpreter):
    current_dir = ""

    def setup(self):
        self.current_dir = os.getcwd()
        os.chdir(os.path.dirname(self.path))

    def build_args(self,filename):
        return [os.path.abspath(self.path), filename]

    def teardown(self):
        os.chdir(current_dir)

class JSRef(Interpreter):
    interp_dir = os.path.join(JSCERT_ROOT_DIR,"interp")
    path = os.path.join(interp_dir,"run_js")
    jsonparser = False

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
        if args.no_parasite:
            arglist.append("-no-parasite")
        return arglist

class Runtest:
    """Main class"""

    filenames = None
    interpreter = None
    handlers = None

    def __init__(self,interpreter):
        self.filenames = []
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

    def run(self):
        # What to do if the user hits control-C
        signal.signal(signal.SIGINT, printer.interrupt_handler)

        # Now let's get down to the business of running the tests
        for handler in self.handlers:
            handler.start_batch()

        for filename in self.filenames:
            testcase = TestCase(filename)
            for handler in self.handlers:
                handler.start_test(testcase)

            self.interpreter.run_test(testcase)

            # Inform handlers of a test result
            # We share the same TestResult among handlers
            for handler in self.handlers:
                handler.finish_test(testcase)

        # Tell handlers that we're done
        for handler in self.handlers:
            handler.end_batch()

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

    VERBOSE = args.verbose
    DEBUG = args.debug

    runtests = Runtests()

    # Tests to run
    for filename in args.filenames:
        runtests.add_path(filename)

    # Interpreter to use
    interpreter = JSRef()
    if interpreter in args:
        interpreter = args.interpreter
    interpreter.set_path(args.interp_path)
    if args.jsonparser:
        interpreter.jsonparser = True
    runtests.set_interpreter(args.interpreter)

    # How to save results
    if(args.dbsave):
        dbmanager = SQLiteDBManager()
    elif(args.psqlconfig):
        dbmanager = PgDBManager()

    runtest.add_handler(CLIResultPrinter())

    if(not args.condor and args.webreport):
        runtests.add_handler(WebResultPrinter())

    runtests.run()

if __name__ == "__main__":
    main()
