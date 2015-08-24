"""
Stub sqlalchemy ORM definition.

Will probably attempt to maintain table relationships in memory
"""


# Helpers
def _(*args, **argvs):
    return None


def _id(x):
    return x

# Constants
Boolean = None
Integer = None
DateTime = None
Interval = None
SmallInteger = None
String = None
Text = None

# Constructors
backref = _
Column = _
column_property = _
Enum = _
ForeignKey = _
MetaData = _
relationship = _

class ModelField(object):
    def __init__(self):
        """Field name that this Descriptor can be accessed from. This should be
        set by the BaseMetaclass on class construction."""
        self.field = None

        """Any fields to be defined on other Tables in this Model"""
        self._pending = {}

    def __get__(self, instance, owner):
        return instance.__dict__.get(self.field, None)

    def __set__(self, instance, value):
        instance.__dict__[self.field] = value

class reference(ModelField):
    def __init__(self, argument, uselist=None, backref=None, **argv):
        self.target = argument
        self.uselist = uselist
        super(reference, self).__init__()

        if isinstance(backref, str):
            self._pending = {self.target: {backref: reference("")}} # FIXME

    def __set__(self, instance, value):
        # Check value is of type self.target

        if self.backref is not None:
            # Directly set the backreference value
            value.__dict__[self.backref] = instance

        # Set our value
        super(reference, self).__set__(instance, value)




class BaseMetaclass(type):
    # Called on Base subclass creation (self is the Base)
    def __init__(self, name, bases, dct):
        #print("__init__(%s, %s, %s, %s)" % (self, name, bases, dct))

        for n, v in dct.items():
            if isinstance(v, ModelField):
                # The field needs to know its name
                v.field = n

                # The field may create cross-referenced fields on other classes
                # Since the field has no information about the class on its
                # creation, it deposits the fields to be created in the
                # _pending field for collection here.
                self._install_fields(v._pending)

        if bases is not ():
            # New model
            self._registry[name] = self

            if name in self._pending:
                dct.update(self._pending[name])
                del self._pending[name]

        return type.__init__(self, name, bases, dct)

    # Functions to be loaded onto BaseMetaclass instances (declarative_base classes)
    def _resolve_subclass(self, subcls):
        """Resolves a subclass identifier (name or reference) to a reference of
        that class"""
        if isinstance(subcls, self._base):
            return subcls
        elif isinstance(subcls, str):
            return self._base._registry.get(subcls)
        else:
            return None

    def _add_pending_fields(self, pending):
        """Adds 'pending' fields onto the named subclasses of Base, or
        places them into the Model's pending list to be installed on the
        subclass' creation."""
        for subcls_name, fields in pending.items():
            subcls = self._resolve_subclass(subcls_name)
            if subcls is not None:
                subcls._install_pending(fields)
            else:
                self._pending_dict_merge(subcls_name, fields)

    def _pending_dict_merge(self, clsname, src):
        dest = self._pending
        if clsname in dest:
            for f, v in src:
                if f in dest[clsname]:
                    raise KeyError("Attempted overwrite of %s in class %s" %
                                (f, clsname))
                else:
                    dest[clsname][f] = v
        else:
            dest[clsname] = src



def declarative_base(*args, **argvs):
    return BaseMetaclass('Base', (), {
        '_registry': {},
        '_pending': {},
    })


# Decorators
hybrid_property = _id
