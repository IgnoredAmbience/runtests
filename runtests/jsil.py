from .interpreter import Interpreter
import os


class JSIL(Interpreter):
    # Class configuration options
    trashesinput = True
    path = './interpreter_run.native'

    # Execution options
    stats = False
    simp = False

    def __init__(self, stats=False, simp=False, **args):
        Interpreter.__init__(self, **args)
        self.stats = stats
        self.simp = simp

    def get_name(self):
        return "JSIL"

    def get_version(self):
        return ""

    def determine_version(self):
        return ""

    def build_args(self, testcase):

        if self.stats:
            arglist = ['/usr/bin/time', '-p', self.path, '-stats']
        else:
            arglist = [self.path, '-test_prelude', self.get_filepath('test_prelude_es6.js')]

        if self.simp:
            arglist.append('-simp')

        arglist.append('-file')
        arglist.append(self.get_filepath(testcase.get_realpath()))

        return arglist

    @staticmethod
    def add_arg_group(argp):
        grp = argp.add_argument_group(title="JSIL Interpreter Options")
        grp.add_argument("--stats", action="store_true",
                         help="Don't execute, just collect and report generated"
                         " program statistics")
        grp.add_argument("--simp", action="store_true",
                         help="Enable IL simplification")
