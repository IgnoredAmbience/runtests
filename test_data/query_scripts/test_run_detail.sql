\x
select
  test_runs.stderr, test_runs.stdout, test_runs.test_id
from
  jscert.test_runs,
  jscert.test_batches,
  jscert.test_cases
where
      test_runs.batch_id = test_batches.id
  AND test_runs.test_id = test_cases.id

  AND test_batches.job_id = 159
  /*AND test_cases.chapter1 >= 8 AND test_cases.chapter1 <= 14*/
  /*AND test_runs.result <> 'PASS'*/
  AND test_cases.chapter1 = 15 and test_cases.chapter2 = 4
  AND test_runs.result = 'FAIL'

  AND test_runs.test_id NOT IN (SELECT test_id FROM jscert.test_group_memberships WHERE group_id > 2)
order by test_id
limit 1
;
