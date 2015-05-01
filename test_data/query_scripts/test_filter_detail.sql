SELECT 
  test_batches.job_id,
  test_runs.test_id,
  test_runs.result,
  fail_groups.description,
  fail_groups.reason
FROM 
  jscert.test_batches,
  jscert.test_runs,
  jscert.test_cases,
  jscert.fail_groups,
  jscert.fail_group_memberships
WHERE 
  test_runs.batch_id = test_batches.id
  AND test_runs.test_id = test_cases.id
  AND test_runs.test_id = fail_group_memberships.test_id
  AND fail_group_memberships.group_id = fail_groups.id

  AND test_batches.job_id = 155
  AND test_cases.chapter1 > 7 AND test_cases.chapter1 < 15
  AND test_runs.result <> 'PASS'
ORDER BY
  test_runs.test_id
;
