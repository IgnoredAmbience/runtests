from . import DB_SCHEMA
from .resulthandler import TestResultHandler
import sys


class DBManager(TestResultHandler):
    engine = None
    sessionmaker = None
    session = None
    wait_for_batch = False

    def __init__(self, connstr=None, schema=None):
        from sqlalchemy import create_engine
        from selalchemy.orm import sessionmaker
        self.engine = create_engine(connstr)
        self.sessionmaker = sessionmaker

        # dbmodels MUST NOT have been imported before here in order for the db
        # schema to take effect
        assert('runtests.dbmodels' not in sys.modules)
        DB_SCHEMA = schema
        self.connect()

    def __del__(self):
        self.disconnect()

    def connect(self):
        self.session = self.sessionmaker(bind=self.engine,
                                         expire_on_commit=False)

    def commit(self):
        self.session.commit()

    def disconnect(self):
        self.session.close()


    #
    def insert_testcases(self, testcases):
        """Bulk inserts testcase data and commits"""
        tcds = map(lambda t: t.db_tc_dict(), testcases)
        self.insert_ignore_many("test_cases", tcds)

    def create_job_batches_runs(self, job):
        self.insert_object(job)
        for batch in job.batches:
            self.insert_object(batch)
            for test in batch.get_testcases():
                self.insert_object(test)
        self.conn.commit()


    # Implementation of TestResultHandler
    def start_batch(self, batch):
        self.commit()

    def finish_test(self, testcase):
        if testcase.duration > 30:
            self.commit()

    def finish_batch(self, batch):
        self.commit()

    # Helper functions
    def insert_ignore_many(self, table, coll):
        # TODO: sqlalchemy implementation
        """Insert or ignore row with colliding ID and commits"""
        raise NotImplementedError

    def insert_object(self, obj):
        self.session.add(obj)

    @staticmethod
    def add_arg_group(argp):
        db_args = argp.add_argument_group(title="Database options")
        db_args.add_argument(
            "--db", action="store", choices=['sqlite', 'postgres'],
            help="Save the results of this testrun to the database")

        db_args.add_argument(
            "--dbpath", action="store", metavar="file", default="",
            help="Path to the database (for SQLite) or configuration file (for "
            "Postgres).")

        db_args.add_argument("--db_init", action="store_true",
                             help="Create the database and load schema")

        db_args.add_argument(
            "--db_pg_schema", action="store", metavar="name", default="jscert",
            help="Schema of Postgres database to use. (Defaults to 'jscert')")

    @staticmethod
    def from_args(args):
        return DBManager(connstr=args., schema=args.db_pg_schema)


# SQLite update_ignore
#        sql = ("INSERT OR IGNORE INTO %s (%s) VALUES (%s)" %
# Postgres update_ignore
#        sql = ("INSERT INTO %s (%s) SELECT %s WHERE NOT EXISTS (SELECT 1 FROM %s WHERE id = %s)" %
#
#        self.cur.execute("LOCK TABLE %s IN SHARE ROW EXCLUSIVE MODE" % table)
#        self.cur.executemany(sql, coll)
#        self.conn.commit()

