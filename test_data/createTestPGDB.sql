CREATE TABLE test_runs (
  id serial primary key
  , time timestamp default 'now'
  , condor_cluster integer
  );
CREATE TABLE test_batch_runs (
  id serial primary key
  , time integer
  , implementation text
  , impl_path text
  , impl_version text
  , title text
  , notes text
  , timestamp integer
  , system text
  , osnodename text
  , osrelease text
  , osversion text
  , hardware text
  , run_id integer references test_runs(id)
  , condor_proc integer
  );
CREATE TABLE single_test_runs (
  id serial primary key
  , test_id text /*references test_cases(filepath)*/
  , batch_id integer references test_batch_runs(id)
  , status text
  , stdout text
  , stderr text
  );
