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
  /*AND test_batches.job_id >= 98
  AND test_runs.result = 'UNKNOWN'*/
  /*AND test_batches.job_id >= 41 and test_batches.job_id <= 93*/
  /*AND test_runs.test_id ~ '^tests/test262/ch(0(8|9)|1(0|1|2|3|4)).*'*/
  /*AND test_cases.chapter1 > 7 AND test_cases.chapter1 < 15*/
  AND test_batches.job_id in (155, 156, 117, 131, 104, 36)
  AND test_cases.chapter1 = 15 and test_cases.chapter2 = 4
GROUP BY
  test_batches.job_id,
  test_runs.result
ORDER BY
  test_batches.job_id
;
