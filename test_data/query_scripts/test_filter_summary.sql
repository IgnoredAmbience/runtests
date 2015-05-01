SELECT 
  test_batches.job_id,
  test_runs.result,
  count(*)
FROM 
  jscert.test_batches, 
  jscert.test_runs,
  jscert.test_cases
WHERE 
  test_runs.batch_id = test_batches.id
  AND test_runs.test_id = test_cases.id
  AND test_batches.job_id in (36, 117, 156)
  AND test_cases.chapter1 > 7 AND test_cases.chapter1 < 15
  AND test_runs.test_id in (select test_id from jscert.test_group_memberships where group_id = 1)
GROUP BY
  test_batches.job_id,
  test_runs.result
ORDER BY
  test_batches.job_id
;
