import unittest
from runtests.sqlalchemystub import (Column, Integer, declarative_base,
                                     ForeignKey, relationship, backref)


class TestSqlAlchemyStub(unittest.TestCase):
    def setUp(self):
        self.Base = declarative_base()

    def oneToMany(self, oneToOne=False):
        class Parent(self.Base):
            __tablename__ = 'parent'
            id = Column(Integer, primary_key=True)
            children = relationship("Child", uselist=(not oneToOne),
                                    backref="parent")

        class Child(self.Base):
            __tablename__ = 'child'
            id = Column(Integer, primary_key=True)
            parent_id = Column(Integer, ForeignKey('parent.id'))

        self.Parent = Parent
        self.Child = Child

    def manyToOne(self, oneToOne=False):
        class Parent(self.Base):
            __tablename__ = 'parent'
            id = Column(Integer, primary_key=True)
            child_id = Column(Integer, ForeignKey('child.id'))
            child = relationship("Child", backref=backref("parents",
                                                          uselist=not oneToOne))

        class Child(self.Base):
            __tablename__ = 'child'
            id = Column(Integer, primary_key=True)

        self.Parent = Parent
        self.Child = Child

    def tearDown(self):
        self.Base = None
        self.Parent = None
        self.Child = None

    def test_one_to_many_forward_set(self):
        self.oneToMany()
        p = self.Parent()
        c1 = self.Child()
        c2 = self.Child()
        self.assertEqual(len(p.children), 0)

        p.children = [c1]
        self.assertEqual(len(p.children), 1)
        self.assertIn(c1, p.children)
        self.assertEqual(c1.parent, p)

        p.children = [c1,c2]
        self.assertEqual(len(p.children), 2)
        self.assertIn(c1, p.children)
        self.assertEqual(c1.parent, p)
        self.assertIn(c2, p.children)
        self.assertEqual(c2.parent, p)

    def test_one_to_many_forward_modify(self):
        self.oneToMany()
        p = self.Parent()
        c1 = self.Child()
        c2 = self.Child()
        self.assertEqual(len(p.children), 0)

        p.children.append(c1)
        self.assertEqual(len(p.children), 1)
        self.assertIn(c1, p.children)
        self.assertEqual(c1.parent, p)

        p.children.append(c2)
        self.assertEqual(len(p.children), 2)
        self.assertIn(c2, p.children)
        self.assertEqual(c2.parent, p)

    def test_one_to_many_forward_remove(self):
        self.oneToMany()
        p = self.Parent()
        c1 = self.Child()
        c2 = self.Child()

        p.children = [c1, c2]
        self.assertEqual(c1.parent, p)
        self.assertEqual(c2.parent, p)

        p.children.remove(c1)
        self.assertNotIn(c1, p.children)
        self.assertIsNone(c1.parent)

    def test_one_to_many_backward_set(self):
        self.oneToMany()
        p = self.Parent()
        c1 = self.Child()
        c2 = self.Child()
        self.assertEqual(len(p.children), 0)

        c1.parent = p
        self.assertEqual(len(p.children), 1)
        self.assertEqual(c1.parent, p)
        self.assertIn(c1, p.children)

        c2.parent = p
        self.assertEqual(len(p.children), 2)
        self.assertEqual(c1.parent, p)
        self.assertIn(c1, p.children)
        self.assertEqual(c2.parent, p)
        self.assertIn(c2, p.children)

    def test_one_to_many_backward_unset(self):
        self.oneToMany()
        p = self.Parent()
        c1 = self.Child()
        c2 = self.Child()
        c1.parent = p
        c2.parent = p
        self.assertEqual(len(p.children), 2)
        self.assertEqual(c1.parent, p)
        self.assertIn(c1, p.children)
        self.assertEqual(c2.parent, p)
        self.assertIn(c2, p.children)

        c1.parent = None
        self.assertEqual(len(p.children), 1)
        self.assertIsNone(c1.parent)
        self.assertNotIn(c1, p.children)

