select
  test_runs.*
from
  jscert.test_runs, jscert.test_batches
where
test_runs.test_id = 'tests/test262/ch15/15.2/15.2.4/15.2.4.4/S15.2.4.4_A1_T3.js'
and test_runs.batch_id = test_batches.id
and test_batches.job_id = 36;