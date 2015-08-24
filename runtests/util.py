from datetime import datetime


class Timer(object):
    def start_timer(self):
        self.start_time = datetime.now()
        self.stop_time = None

    def stop_timer(self):
        if not self.start_time:
            raise Exception('Timer not started')
        self.stop_time = datetime.now()
        self.duration = self.get_delta().total_seconds()

    def get_delta(self):
        if not self.start_time or not self.stop_time:
            raise Exception('Timer not stopped')
        return self.stop_time - self.start_time


class SubclassSelectorMixin(object):

    """Mixin to assist selecting and constructing a subclass from command line
    arguments"""

    """If set, will offer the root cls for construction"""
    __generic_name__ = None

    def __init__(self, **nargs):
        raise NotImplementedError()

    @classmethod
    def Construct(cls, name, args={}):
        """Construct the appropriate subclass instance of name, using the
        an arguments object"""
        # pylint: disable=no-member
        name = name.lower()

        if cls.__generic_name__ and name == cls.__generic_name__.lower():
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
