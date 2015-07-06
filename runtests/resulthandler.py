from __future__ import print_function
import getpass
import os
import time
import urllib

try:
    import pystache
except ImportError as e:
    pystache = None


class TestResultHandler(object):

    """
    Recieves notifications of events in the test cycle

    A test is the execution of an individual test file
    A test batch it is a number of sequential executions of tests
    A test job is a collection of test batches, it may only use one interpreter
    """

    def start_job(self, job):
        """Called when a job begins executing"""
        pass

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

    def finish_job(self, job):
        """Called once a job has finished running"""
        pass

    def interrupt_handler(self):
        """Called on a handler when the test run is terminating due to SIGINT"""
        pass

class CLIResultPrinter(TestResultHandler):
    # Some pretty colours for our output messages.
    NORMAL = "\033[00m"
    HEADING = "\033[35m"
    PASS = "\033[32m"
    FAIL = "\033[31m"
    ABANDON = "\033[33m"

    verbose = False
    failed = False

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
        elif testcase.timeout():
            self.print_abandon("Timed out...")
        else:
            self.print_abandon("Something really weird happened")

        if self.verbose:
            print("Exit code: %s" % (testcase.exit_code,))
            print("Test is negative? %s" % (testcase.is_negative(),))
            print("=== STDOUT ===")
            print(testcase.stdout)
            print("=== STDERR ===")
            print(testcase.stderr)

    def print_heading(self, s):
        print(self.HEADING + s + self.NORMAL)

    def print_pass(self, s):
        print(self.PASS + s + self.NORMAL)

    def print_fail(self, s):
        print(self.FAIL + s + self.NORMAL)

    def print_abandon(self, s):
        print(self.ABANDON + s + self.NORMAL)

    def finish_batch(self, batch):
        if len(batch.failed_tests) > 0:
            self.failed = True
            print("The following tests failed:")
            for failure in batch.failed_tests:
                print(failure.filename)
        if len(batch.aborted_tests) > 0:
            self.failed = True
            print("The following tests were abandoned")
            for abandoned in batch.aborted_tests:
                print(abandoned.filename)
        print ("There were %d passes, %d fails, and %d abandoned tests." %
               (len(batch.passed_tests), len(batch.failed_tests), len(batch.aborted_tests)))

    def get_exit_code(self):
        return 1 if self.failed else 0


class WebResultPrinter(TestResultHandler):

    """
    This class maintains the results of our test run, and generates a html report
    """

    # Configuration
    templatedir = ""
    reportdir = ""
    noindex = False

    def __init__(self, templatedir, reportdir, noindex):
        if not pystache:
            raise ImportError(
                "%s: pystache is required for web reports" % e.message)

        self.noindex = noindex
        self.set_paths(templatedir, reportdir)

    def set_paths(self, templatedir, reportdir):
        """Check all files required for html output exist before we begin"""
        templates = ["template.tmpl", "test_results.tmpl"]
        if not self.noindex:
            templates.append("index.tmpl")

        for f in templates:
            p = os.path.join(templatedir, f)
            if not os.access(p, os.R_OK):
                raise Exception(
                    "Required html template %s is not readable." % p)

        if not os.access(reportdir, os.W_OK):
            raise Exception(
                "Report output directory %s is not writable." % reportdir)
        if not self.noindex:
            p = os.path.join(reportdir, "index.html")
            if os.path.isfile(p) and not os.access(p, os.W_OK):
                raise Exception("Report index file %s not writable." % p)

        self.templatedir = templatedir
        self.reportdir = reportdir

    def finish_batch(self, batch):
        self.produce_web_page(batch.make_report())

    def produce_web_page(self, report):
        simplerenderer = pystache.Renderer(escape=lambda u: u)
        with open(os.path.join(self.templatedir, "template.tmpl"), "r") as outer:
            with open(os.path.join(self.templatedir, "test_results.tmpl"), "r") as template:
                outfilenamebits = [
                    "report", getpass.getuser(), report['implementation']]
                if report['testtitle']:
                    outfilenamebits.append(report['testtitle'])
                outfilenamebits.extend(
                    [time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())])
                outfilename = "-".join(outfilenamebits) + ".html"
                with open(os.path.join(self.reportdir, outfilename), "w") as outfile:
                    outfile.write(simplerenderer.render(
                        outer.read(), {"body": pystache.render(template.read(), report)}))

        if not self.noindex:
            self.index_reports()

    def index_reports(self):
        # Get a list of all non-index html files in the reportdir
        filenames = filter(lambda x: x != "index.html", filter(
            lambda x: x.endswith(".html"), os.listdir(self.reportdir)))
        filenames.sort()
        filenames = map(lambda x: {"linkname": os.path.basename(
            x), "filename": urllib.quote(os.path.basename(x))}, filenames)
        simplerenderer = pystache.Renderer(escape=lambda u: u)
        with open(os.path.join(self.templatedir, "template.tmpl"), "r") as outer:
            with open(os.path.join(self.templatedir, "index.tmpl"), "r") as template:
                with open(os.path.join(self.reportdir, "index.html"), "w") as outfile:
                    outfile.write(simplerenderer.render(
                        outer.read(), {"body": pystache.render(template.read(), {"testlist": filenames})}))
