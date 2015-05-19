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
  AND test_batches.job_id in (159)
  AND test_cases.chapter1 = 15 AND test_cases.chapter2 = 4
GROUP BY
  test_batches.job_id,
  test_runs.result
ORDER BY
  test_batches.job_id,
  test_runs.result
;
