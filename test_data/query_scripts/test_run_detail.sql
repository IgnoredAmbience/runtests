\x
select
  test_runs.*
from
  jscert.test_runs,
  jscert.test_batches,
  jscert.test_cases
where
      test_runs.batch_id = test_batches.id
  AND test_runs.test_id = test_cases.id

  AND test_batches.job_id = 156
  AND test_cases.chapter1 >= 8 AND test_cases.chapter1 <= 14
  /*AND test_runs.result <> 'PASS'*/
  AND test_runs.test_id in (select test_id from jscert.test_group_memberships where group_id = 8)
  order by test_id
;
