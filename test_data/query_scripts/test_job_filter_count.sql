SELECT
  test_groups.description,
  count(*)
FROM
  jscert.test_runs,
  jscert.test_batches,
  jscert.test_group_memberships,
  jscert.test_groups
WHERE
      test_runs.batch_id = test_batches.id
  AND test_runs.test_id = test_group_memberships.test_id
  AND test_groups.id = test_group_memberships.group_id

  AND job_id = 159
  AND result <> 'PASS'
  AND group_id > 2
GROUP BY
  test_groups.description
;
