SELECT 
  test_batches.job_id,
  test_runs.test_id,
  test_runs.result
FROM 
  jscert.test_batches,
  jscert.test_runs,
  jscert.test_cases
WHERE 
  test_runs.batch_id = test_batches.id
  AND test_runs.test_id = test_cases.id
  AND test_runs.test_id not in (select test_id from jscert.fail_group_memberships)

  AND test_batches.job_id = /* 155 */ 36
  AND test_cases.chapter1 > 7 AND test_cases.chapter1 < 15
  AND test_runs.result <> 'PASS'
ORDER BY
  test_runs.test_id
;
