import logging
import os
import shutil
import sys
import tempfile

if sys.version_info < (3, 3):
    # Use backported subprocess stdlib for timeout functionality
    import subprocess32 as subprocess
else:
    import subprocess

from main import JSCERT_ROOT_DIR

class Interpreter(object):
    """Base class for Interpreter calling methods"""
    pass_code = 0
    fail_code = 1
    path = ""
    version = "Version unknown"
    arg_name = "generic"
    timeout = None

    trashesinput = False
    tmpdir = None

    PASS = 0
    FAIL = 1
    ABORT = 2
    TIMEOUT = 3

    @classmethod
    def Construct(cls, name, *args):
        # pylint: disable=no-member
        for subcls in Interpreter.__subclasses__():
            if name.lower() == subcls.__name__.lower():
                return subcls(*args)
        return cls(*args)

    @classmethod
    def Types(cls):
        # pylint: disable=no-member
        interps = map(lambda c: c.__name__.lower(), Interpreter.__subclasses__())
        interps.append("generic")
        return interps

    def __init__(self):
        if self.trashesinput:
            self.tmpdir = tempfile.mkdtemp()

    def get_name(self):
        return os.path.basename(self.path)

    def get_version(self):
        return self.version

    def set_version(self, version=""):
        if version:
            self.version = version
        else:
            self.version = self.determine_version()

    def set_parser(self):
        pass

    def determine_version(self):
        if self.path:
            try:
                output = subprocess.check_output([self.path, "--version"])
                return output.strip()
            except:
                return "Unknown version"
        else:
            return "Unknown version"

    def set_path(self, path):
        if path:
            self.path = path

    def set_timeout(self, timeout):
        self.timeout = timeout

    def setup(self):
        pass

    def build_args(self, testcase):
        return [self.path, testcase.get_realpath()]

    """Get path to an input file, copying it to temporary storage to prevent race conditons, if required"""
    def get_filepath(self, path, *paths):
        filepath = os.path.join(path, *paths)

        """Todo: Adjust so copies for concurrent task running only"""
        if self.trashesinput:
            base = os.path.basename(filepath)
            tmpfile = os.path.join(self.tmpdir, base)
            shutil.copy(filepath, tmpfile)
            return tmpfile
        else:
            return filepath

    def run_test(self, testcase):
        """Mutates testcase with appropriate result"""
        result = None

        self.setup()
        command = self.build_args(testcase)
        logging.debug("Calling interpreter with the command: %s", command)

        testcase.start_timer()
        test_pipe = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            output,errors = test_pipe.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            test_pipe.kill()
            output,errors = test_pipe.communicate()
            result = Interpreter.TIMEOUT
        testcase.stop_timer()

        output = output.decode("utf8").encode("ascii","xmlcharrefreplace")
        errors = errors.decode("utf8").encode("ascii","xmlcharrefreplace")
        ret = test_pipe.returncode
        if not result:
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
    parser_path = os.path.join(interp_dir,"parser","lib","js_parser.jar")
    arg_name = "jsref"
    no_parasite = False
    jsonparser = False
    trashesinput = True

    def __init__(self, no_parasite=False, jsonparser=False):
        Interpreter.__init__(self)
        self.no_parasite = no_parasite
        self.jsonparser = jsonparser

    def get_name(self):
        return "JSRef"

    def set_parser(self, parser=""):
        if parser:
            self.parser_path = parser

    def build_args(self, testcase):
        # Normally we run a test like this:
        #./interp/run_js -jsparser interp/parser/lib/js_parser.jar -test_prelude interp/test_prelude.js -file filename
        # But if this is a LambdaS5 test, we need additional kit, like this:
        # ./interp/run_js -jsparser interp/parser/lib/js_parser.jar -test_prelude interp/test_prelude.js -test_prelude tests/LambdaS5/lambda-pre.js -test_prelude filename -file tests/LambdaS5/lambda-post.js
        # We can tell if it's a LambdaS5 test, because those start with "tests/LambdaS5/unit-tests/".
        # In addition, we may want to add some debug flags.
        arglist = [self.path, "-jsparser", self.parser_path]
        if self.jsonparser:
            arglist.append("-json")
        #if DEBUG:
        #    arglist.append("-print-heap")
        #    arglist.append("-verbose")
        #    arglist.append("-skip-init")
        arglist.append("-test_prelude")
        arglist.append(self.get_filepath("interp","test_prelude.js"))
        if testcase.isLambdaS5Test():
            arglist.append("-test_prelude")
            arglist.append(self.get_filepath("tests/LambdaS5/lambda-pre.js"))
            arglist.append("-test_prelude")
            arglist.append(self.get_filepath(testcase.get_realpath()))
            arglist.append("-file")
            arglist.append(self.get_filepath("tests/LambdaS5/lambda-post.js"))
        elif testcase.isSpiderMonkeyTest():
            arglist.append("-test_prelude")
            arglist.append(self.get_filepath("interp/test_prelude_SpiderMonkey.js"))
            arglist.append("-test_prelude")
            arglist.append(self.get_filepath("tests/SpiderMonkey/tests/shell.js"))
            arglist.append("-file")
            arglist.append(self.get_filepath(testcase.get_realpath()))
        elif testcase.usesInclude():
            arglist.append("-test_prelude")
            arglist.append(self.get_filepath("interp/libloader.js"))
            arglist.append("-file")
            arglist.append(self.get_filepath(testcase.get_realpath()))
        else:
            arglist.append("-file")
            arglist.append(self.get_filepath(testcase.get_realpath()))
        if self.no_parasite:
            arglist.append("-no-parasite")
        return arglist
