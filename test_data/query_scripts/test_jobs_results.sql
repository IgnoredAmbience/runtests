SELECT
  test_jobs.id,
  test_jobs.title,
  test_jobs.note,
  test_jobs.impl_version,
  count(test_runs.result = 'PASS' OR NULL) AS "pass",
  count(test_runs.result = 'FAIL' OR NULL) AS "fail",
  count(test_runs.result = 'ABORT' OR NULL) AS "abort",
  count(test_runs.result = 'UNKNOWN' OR NULL) AS "unknown",
  count(*) AS "total"
FROM
  jscert.test_jobs,
  jscert.test_batches,
  jscert.test_runs,
  jscert.test_cases
WHERE
  test_runs.batch_id = test_batches.id
  AND test_jobs.id = test_batches.job_id
  AND test_cases.id = test_runs.test_id
  /*AND test_cases.chapter1 > 7 AND test_cases.chapter1 < 15*/
  AND test_cases.chapter1 = 15 AND test_cases.chapter2 = 4
  AND test_jobs.id IN (117, 155, 159, 160)
GROUP BY
  test_jobs.id
HAVING
  count(test_runs.result = 'UNKNOWN' OR NULL) != count(*)
ORDER BY
  test_jobs.id
;
