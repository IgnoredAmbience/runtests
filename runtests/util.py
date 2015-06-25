from datetime import datetime

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

class SubclassSelector(object):
    """Mixin to assist selecting and constructing a subclass from command line arguments"""
    @classmethod
    def Construct(cls, name, *args):
        # pylint: disable=no-member
        name = name.lower()
        if name == "generic":
            return cls(*args)
        for subcls in cls.__subclasses__():
            if name == subcls.__name__.lower():
                return subcls(*args)
        raise ValueError("Failure constructing %s: subclass %s is not known." %
                  (cls.__name__, name))

    @classmethod
    def Types(cls):
        # pylint: disable=no-member
        return [cls] + cls.__subclasses__()

    @classmethod
    def TypesStr(cls):
        # pylint: disable=no-member
        interps = ['generic'] + [c.__name__.lower() for c in cls.__subclasses__()]
        return interps

