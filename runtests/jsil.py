from .interpreter import Interpreter
import os


class JSIL(Interpreter):
    # Class configuration options
    trashesinput = False

    def __init__(self, **args):
        Interpreter.__init__(self, **args)
        self.path = './jsil.native'

    def get_name(self):
        return "JSIL"

    def get_version(self):
        return ""

    def determine_version(self):
        return ""

    def set_path(self, path):
        self.path = os.path.abspath(path)

    def setup(self):
        # TODO: Use cwd parameter of Popen instead of chdir-ing??
        self.current_dir = os.getcwd()
        os.chdir(os.path.dirname(self.path))

    def build_args(self, testcase):
        arglist = [self.path, '-test262', '-silent', '-file']
        arglist.append(self.get_filepath(testcase.get_realpath()))
        return arglist

    def teardown(self):
        os.chdir(self.current_dir)
