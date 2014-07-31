/* Mostly compatible with both sqlite and postgres, except:
   * All serial types must be replaced with integers, and autoincrement appended to the line
   * SQLite doesn't do enums, it errors on the CREATE TYPE line, this is safe to ignore.
     It defaults to text mode for the field due to the _text suffix of the type name
*/

CREATE TYPE result_text AS ENUM ('PASS', 'FAIL', 'ABORT'); /* safe to ignore error for sqlite */

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
  ( filepath text primary key  /* path is relative to jscert root directory */
  , negative boolean
  );

CREATE TABLE test_runs
  ( id integer primary key autoincrement
  , test_id text references test_cases(filepath)
  , batch_id integer references test_batches(id)
  , result result_text
  , exit_code smallint
  , stdout text
  , stderr text
  );

CREATE TABLE test_groups
  ( id integer primary key autoincrement
  , description text
  );

CREATE TABLE test_group_memberships
  ( group_id integer references test_groups(id)
  , test_id text references test_cases(filepath)
  );

CREATE TABLE fail_groups
  ( id integer primary key autoincrement
  , description text
  , reason text
  );

CREATE TABLE fail_group_memberships
  ( group_id integer references fail_groups(id)
  , test_id text references test_cases(filepath)
  );
