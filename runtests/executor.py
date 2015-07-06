from .resulthandler import TestResultHandler
from .util import SubclassSelectorMixin


class Executor(SubclassSelectorMixin):

    """Base class for different test execution strategies, for example:
    sequential, multi-threaded, distributed with Condor"""

    __generic_name__ = None

    stopping = False
    handlers = None
    batch_size = 0

    def __init__(self, batch_size=0, **nargs):
        self.handlers = []
        self.batch_size = batch_size

    def add_handler(self, handler):
        if not handler:
            return
        if not isinstance(handler, TestResultHandler):
            raise TypeError("%s is not a TestResultHandler" % (handler,))
        self.handlers.append(handler)

    def get_batch_size(self):
        """Allows the executor the option to override the user's chosen batch
        size if the option is not recognised"""
        return self.batch_size

    def run_job(self, job):
        raise NotImplemented

    def _run_job(self, job):
        """Override this method to implement a custom test batch dispatch"""

        for handler in self.handlers:
            handler.start_job(job)

        job.start_timer()
        for batch in job.batches:
            self.run_batch(batch)
        job.stop_timer()

        for handler in self.handlers:
            handler.finish_job(job)

    def run_batch(self, batch):
        raise NotImplemented

    def _run_batch(self, batch):
        batch.set_machine_details()

        for handler in self.handlers:
            handler.start_batch(batch)

        batch.start_timer()

        # Now let's get down to the business of running the tests
        while batch.has_testcase():
            testcase = batch.get_testcase()
            for handler in self.handlers:
                handler.start_test(testcase)

            # FIXME: Too much indirection
            batch.job.interpreter.run_test(testcase)

            # FIXME: move this closer to run_test? Or testcase?
            batch.test_finished(testcase)

            # Inform handlers of a test result
            # We share the same TestResult among handlers
            for handler in self.handlers:
                handler.finish_test(testcase)

        batch.stop_timer()

        # Tell handlers that we're done
        for handler in self.handlers:
            handler.finish_batch(batch)

    def stop(self):
        if self.stopping:
            return

        self.stopping = True

        # TODO: Stop stuff

        for handler in self.handlers:
            handler.interrupt_handler()

    @staticmethod
    def add_arg_group(argp):
        """Called to add arguments to the CLI, subclasses should override this"""
        pass


class Sequential(Executor):

    def get_batch_size(self):
        """Sequential executors run using 1 batch of unbounded size"""
        return 0

    def run_job(self, job):
        return self._run_job(job)

    def run_batch(self, batch):
        return self._run_batch(batch)

