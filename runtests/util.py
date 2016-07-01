from datetime import datetime
import logging
import sys

if sys.version_info < (3, 3):
    # Use backported subprocess stdlib for timeout functionality
    import subprocess32 as subprocess
else:
    import subprocess


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


class SubclassSelectorMixin(object):

    """Mixin to assist selecting and constructing a subclass from command line
    arguments"""

    """If set, will offer the root cls for construction"""
    __generic_name__ = None

    def __init__(self, **nargs):
        raise NotImplemented

    @classmethod
    def Construct(cls, name, args):
        """Construct the appropriate subclass instance of name, using the
        an arguments object"""
        # pylint: disable=no-member
        name = name.lower()

        if cls.__generic_name__ and name == cls.__generic_name__:
            return cls(**vars(args))

        for subcls in cls.__subclasses__():
            if name == subcls.__name__.lower():
                return subcls(**vars(args))

        raise ValueError("Failure constructing %s: subclass %s is not known." %
                         (cls.__name__, name))

    @classmethod
    def Types(cls):
        # pylint: disable=no-member
        types = [cls] if cls.__generic_name__ else []
        return types + cls.__subclasses__()

    @classmethod
    def TypesStr(cls):
        # pylint: disable=no-member
        types = [cls.__generic_name__] if cls.__generic_name__ else []
        return types + [c.__name__.lower() for c in cls.__subclasses__()]

    @staticmethod
    def add_arg_group(argp):
        """Called to add arguments to the CLI, subclasses could override this"""
        pass


class MaxLevelFilter(logging.Filter):
    """
    This is a logging filter that ignores log records above a certain level.
    """

    def __init__(self, maxlevel):
        self.maxlevel = maxlevel

    def filter(self, record):
        return record.levelno < self.maxlevel


def get_git_version(dir=None):
    hash = ''
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=dir)
        hash = out.strip()
    finally:
        return hash
