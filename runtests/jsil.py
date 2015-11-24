from .interpreter import Interpreter


class JSIL(Interpreter):
    # Class configuration options
    trashesinput = True
    path = 'interpreter_run.byte'

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

    def build_args(self, testcase):
        arglist = [self.path, '-test_prelude', self.get_filepath('test_prelude.js')]
        if self.stats:
            arglist.append('-stats')

        if self.simp:
            arglist.append('-simp')

        arglist.append('-file')
        arglist.append(self.get_filepath(testcase.get_realpath()))

        return arglist
