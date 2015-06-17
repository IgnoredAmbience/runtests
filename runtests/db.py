import os
import re
import sqlite3
try:
    import psycopg2
except ImportError:
    psycopg2 = None

from resulthandler import TestResultHandler
from main import JSCERT_ROOT_DIR

DB_SCHEMA_LOCATION = os.path.join(
    JSCERT_ROOT_DIR, 'test_data', 'createTestDB.sql')


class DBManager(TestResultHandler):
    conn = None
    cur = None
    wait_for_batch = False

    def __del__(self):
        self.disconnect()

    def connect(self):
        """Only implement for db backends with limited connection pools"""
        pass

    def disconnect(self):
        """Only implement for db backends with limited connection pools, or require explicit commit"""
        pass

    def insert_testcases(self, testcases):
        """Bulk inserts testcase data and commits"""
        tcds = map(lambda t: t.db_tc_dict(), testcases)
        self.insert_ignore_many("test_cases", tcds)

    def create_job_batches_runs(self, job):
        self.insert_object(job)
        for batch in job.get_batches():
            self.insert_object(batch)
            for test in batch.get_testcases():
                self.insert_object(test)
        self.conn.commit()

    def start_batch(self, batch):
        self.connect()
        self.update_object(batch)
        self.conn.commit()
        if self.wait_for_batch:
            self.disconnect()

    def start_test(self, testcase):
        pass

    def finish_test(self, testcase):
        if not self.wait_for_batch:
            self.update_object(testcase)
            self.conn.commit()

    def finish_batch(self, batch):
        self.connect()
        if self.wait_for_batch:
            self.update_objects(batch.get_finished_testcases())
        self.update_object(batch)
        self.conn.commit()
        self.disconnect()

    # Helper functions
    def build_fields_insert(self, fields):
        """
        Builds a field list pattern to substitute into a SQL statement, eg:
        ["a","b","c"] ==> [ "a, b, c", ":a, :b, :c" ]
        """
        key_pairs = map(lambda k: (k, self.subst_pattern(k)), fields)
        key_lists = zip(*key_pairs)
        key_strings = map(", ".join, key_lists)
        return key_strings

    def build_fields_update(self, fields):
        """
        Builds a field list pattern to substitute into a SQL statement, eg:
        ["a","b","c"] ==> [ "a = :a, b = :b, c = :c" ]
        """
        assigns = map(lambda k: "%s = %s" % (k, self.subst_pattern(k)), fields)
        return ", ".join(assigns)

    def insert(self, table, dic):
        """Retrieval of inserted id is implementation-specific"""
        raise NotImplementedError

    def insert_many(self, table, coll):
        (fnames, fsubst) = self.build_fields_insert(coll[0].keys())
        sql = ("INSERT INTO %s (%s) VALUES (%s)" % (table, fnames, fsubst))
        self.cur.executemany(sql, coll)

    def insert_ignore_many(self, table, coll):
        """Insert or ignore row with colliding ID and commits"""
        raise NotImplementedError

    def insert_object(self, obj):
        if not obj._table:
            raise Exception("Object not suitable for database insertion")
        else:
            obj._dbid = self.insert(obj._table, obj.db_dict())

    def update(self, table, dic):
        if "id" not in dic:
            raise Exception("Needs id field")
        self.update_many(table, [dic])

    def update_many(self, table, coll):
        """Expects dbid to be set on all dicts being passed in for updating"""
        assigns = self.build_fields_update(coll[0].keys())
        sql = ("UPDATE %s SET %s WHERE id = %s" %
               (table, assigns, self.subst_pattern("id")))
        self.cur.executemany(sql, coll)

    def update_object(self, obj):
        if not obj._table:
            raise Exception("Object not suitable for database insertion")
        else:
            self.update(obj._table, obj.db_dict())

    def update_objects(self, objs):
        """Assumes all objects passed in are of same class"""
        table = objs[0]._table
        dicts = map(lambda o: o.db_dict(), objs)
        self.update_many(table, dicts)

    def import_schema(self):
        with open(DB_SCHEMA_LOCATION, 'r') as f:
            sql = f.read()
        sql = self.prepare_schema(sql)
        self.execute_script(sql)
        self.conn.commit()

    def execute_script(self, sql):
        self.cur.execute(sql)

    def prepare_schema(self, sql):
        return sql

    def subst_pattern(self, field):
        raise NotImplementedError


class SQLiteDBManager(DBManager):

    def __init__(self, path, initing=False):
        if not initing and not os.path.isfile(path):
            raise Exception(
                "Database not found at %s\nPlease create the database using --db_init before using it." % path)
        self.conn = sqlite3.connect(path)
        self.cur = self.conn.cursor()

    def subst_pattern(self, field):
        return (":%s" % field)

    def insert(self, table, dic):
        (fnames, fsubst) = self.build_fields_insert(dic.keys())
        sql = ("INSERT INTO %s (%s) VALUES (%s)" % (table, fnames, fsubst))
        self.cur.execute(sql, dic)
        return self.cur.lastrowid

    def insert_ignore_many(self, table, coll):
        """Insert or ignore rows with colliding ID and commits"""
        (fnames, fsubst) = self.build_fields_insert(coll[0].keys())
        sql = ("INSERT OR IGNORE INTO %s (%s) VALUES (%s)" %
               (table, fnames, fsubst))
        self.cur.executemany(sql, coll)
        self.conn.commit()

    def execute_script(self, sql):
        self.cur.executescript(sql)


class PostgresDBManager(DBManager):
    connstr = ""
    schema = ""

    def __init__(self, connstr, schema=""):
        if not psycopg2:
            raise ImportError
        self.connstr = connstr
        self.schema = schema

    def connect(self):
        if (not self.conn) or (self.conn.closed != 0):
            self.conn = psycopg2.connect(self.connstr)
            self.cur = self.conn.cursor()
            if self.schema:
                self.cur.execute("SET SCHEMA %s", (self.schema,))
                self.conn.commit()

    def disconnect(self):
        if self.cur:
            self.cur.close()
            self.cur = None
        if self.conn:
            self.conn.commit()
            self.conn.close()
            self.conn = None

    def subst_pattern(self, field):
        return ("%%(%s)s" % field)

    def insert(self, table, dic):
        (fnames, fsubst) = self.build_fields_insert(dic.keys())
        sql = ("INSERT INTO %s (%s) VALUES (%s) RETURNING id" %
               (table, fnames, fsubst))
        self.cur.execute(sql, dic)
        return self.cur.fetchone()[0]

    def insert_ignore_many(self, table, coll):
        """Insert or ignore rows with colliding ID, and commits"""
        (fnames, fsubst) = self.build_fields_insert(coll[0].keys())
        sql = ("INSERT INTO %s (%s) SELECT %s WHERE NOT EXISTS (SELECT 1 FROM %s WHERE id = %s)" %
               (table, fnames, fsubst, table, self.subst_pattern("id")))

        self.cur.execute("LOCK TABLE %s IN SHARE ROW EXCLUSIVE MODE" % table)
        self.cur.executemany(sql, coll)
        self.conn.commit()

    def prepare_schema(self, sql):
        if self.schema:
            try:
                self.cur.execute("CREATE SCHEMA %s" % (self.schema,))
            except psycopg2.ProgrammingError as e:
                raise Exception("Could not create schema: %s" % (e,))
        sql = re.sub(r"/\*\*\* POSTGRES ONLY \*\*\* (.*) \*\*\*/", r"\1", sql)
        sql = re.sub(r"(.*)integer(.*) autoincrement", r"\1serial\2", sql)
        return sql


class DBObject(object):
    _table = ""
    _dbid = 0

    def db_dict(self):
        dic = self._db_dict()
        if self._dbid:
            dic['id'] = self._dbid
        return dic

    def _db_dict(self):
        raise NotImplementedError
