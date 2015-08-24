import unittest
import time
from datetime import datetime, timedelta
from runtests.util import Timer, SubclassSelectorMixin


class TestTimer(unittest.TestCase):
    def test_timer_sets_start_time(self):
        timer = Timer()
        timer.start_timer()
        self.assertIsInstance(timer.start_time, datetime)
        self.assertIsNone(timer.stop_time)

    def test_timer_sets_stop_time(self):
        timer = Timer()
        timer.start_timer()
        timer.stop_timer()
        self.assertIsInstance(timer.start_time, datetime)
        self.assertIsInstance(timer.stop_time, datetime)

    def test_timer_sets_duration(self):
        timer = Timer()
        timer.start_timer()
        time.sleep(0.1)
        timer.stop_timer()
        self.assertGreater(timer.duration, 0)

    def test_timer_get_delta(self):
        timer = Timer()
        timer.start_timer()
        time.sleep(0.1)
        timer.stop_timer()
        delta = timer.get_delta()
        self.assertIsInstance(delta, timedelta)

    def test_timer_delta_equals_duration(self):
        timer = Timer()
        timer.start_timer()
        time.sleep(0.1)
        timer.stop_timer()
        delta = timer.get_delta()
        self.assertEqual(delta.total_seconds(), timer.duration)

    def test_timer_stop_exception(self):
        timer = Timer()
        with self.assertRaises(Exception):
            timer.stop_timer()

    def test_timer_get_delta_exception(self):
        timer = Timer()
        with self.assertRaises(Exception):
            timer.get_delta()


class EmptyArguments(object):
    pass


class Parent0(SubclassSelectorMixin):
    def __init__(self, **nargs):
        pass


class Child00(Parent0):
    pass


class Child01(Parent0):
    pass


class Parent1(SubclassSelectorMixin):
    __generic_name__ = "Parent 1"

    def __init__(self, **nargs):
        pass


class Child10(Parent1):
    pass


class Child11(Parent1):
    pass


class TestSubclassSelectorMixin(unittest.TestCase):
    def assertIterPerm(self, a, b):
        """Asserts that the two iterables have the same contents"""
        self.assertSetEqual(frozenset(a), frozenset(b))

    def test_construct_should_fail(self):
        with self.assertRaises(Exception):
            SubclassSelectorMixin()

    def test_types_exclude_parent(self):
        self.assertIterPerm(Parent0.Types(),
                            [Child00, Child01])

    def test_types_include_parent(self):
        self.assertIterPerm(Parent1.Types(),
                            [Parent1, Child10, Child11])

    def test_types_str_exclude_parent(self):
        self.assertIterPerm(Parent0.TypesStr(),
                            ["child00", "child01"])

    def test_types_str_include_parent(self):
        self.assertIterPerm(Parent1.TypesStr(),
                            ["Parent 1", "child10", "child11"])

    def test_construct_excluded_parent_should_fail(self):
        with self.assertRaises(ValueError):
            Parent0.Construct("Parent0")

    def test_construct_nonexistant_class_should_fail(self):
        with self.assertRaises(ValueError):
            Parent0.Construct("notexist")

    def assertConstruct(self, parent, string, child):
        self.assertIsInstance(parent.Construct(string, EmptyArguments()), child)

    def test_construct_child(self):
        self.assertConstruct(Parent0, "child00", Child00)
        self.assertConstruct(Parent0, "child01", Child01)
        self.assertConstruct(Parent1, "child10", Child10)
        self.assertConstruct(Parent1, "child11", Child11)

    def test_construct_parent(self):
        self.assertConstruct(Parent1, "Parent 1", Parent1)

    # TODO: assertions for argument passing
