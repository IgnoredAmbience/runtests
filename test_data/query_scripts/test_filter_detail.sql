SELECT
  --test_batches.job_id,
  test_runs.test_id,
  test_runs.result,
  test_groups.description,
  test_runs.stdout,
  test_runs.stderr
FROM
  jscert.test_runs,
  jscert.test_batches,
  jscert.test_cases,
  jscert.test_groups,
  jscert.test_group_memberships
WHERE
  test_runs.batch_id = test_batches.id
  AND test_runs.test_id = test_cases.id
  AND test_runs.test_id = test_group_memberships.test_id
  AND test_group_memberships.group_id = test_groups.id

  AND test_batches.job_id = 159
  --AND test_cases.chapter1 > 7 AND test_cases.chapter1 < 15
  AND test_cases.chapter1 = 15 AND test_cases.chapter2 = 4
  AND test_runs.result <> 'PASS'
  AND group_id IN (8, 30, 31)
ORDER BY
  test_runs.test_id
;
