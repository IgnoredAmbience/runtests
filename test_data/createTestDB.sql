/*
Testing database schema. Import using:
  runtests.py --createdb

If doing a manual import read these notes:
Mostly compatible with both sqlite and postgres, except:
   * Postgres doesn't do autoincrement, run this regexp search and replace:
      s/\(.*\)integer\(.*\) autoincrement/\1serial\2/
   * SQLite doesn't do schemas.
   * SQLite doesn't do enums, it errors on the CREATE TYPE line, this is safe to ignore.
     It defaults to text mode for the field due to the _text suffix of the type name
The autoincrement and *** POSTGRES ONLY *** lines are modified appropriately by the runtests.py
database create command.
*/
/*** POSTGRES ONLY *** CREATE TYPE result_text AS ENUM ('PASS', 'FAIL', 'ABORT'); ***/

CREATE TABLE test_jobs
  ( id integer primary key autoincrement
  , title text
  , note text
  , impl_name text
  , impl_version text
  , create_time timestamp
  , repo_version text
  , username text
  , condor_cluster smallint
  , condor_scheduler text
  );

CREATE TABLE test_batches
  ( id integer primary key autoincrement
  , job_id integer references test_jobs(id)
  , system text
  , osnodename text
  , osrelease text
  , osversion text
  , hardware text
  , start_time timestamp
  , end_time timestamp
  , condor_proc smallint
  );

CREATE TABLE test_cases
  ( id text primary key  /* path is relative to jscert root directory */
  , negative boolean
  );

CREATE TABLE test_runs
  ( id integer primary key autoincrement
  , test_id text references test_cases(id)
  , batch_id integer references test_batches(id)
  , result result_text
  , exit_code smallint
  , stdout text
  , stderr text
  , duration integer
  );

CREATE TABLE test_groups
  ( id integer primary key autoincrement
  , description text
  );

CREATE TABLE test_group_memberships
  ( group_id integer references test_groups(id)
  , test_id text references test_cases(id)
  );

CREATE TABLE fail_groups
  ( id integer primary key autoincrement
  , description text
  , reason text
  );

CREATE TABLE fail_group_memberships
  ( group_id integer references fail_groups(id)
  , test_id text references test_cases(id)
  );
