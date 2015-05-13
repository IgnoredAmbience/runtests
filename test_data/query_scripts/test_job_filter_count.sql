SELECT
  COALESCE(test_groups.description, 'TODO: Not yet classified') des,
  count(*)
FROM
  (jscert.test_group_memberships RIGHT OUTER JOIN jscert.test_runs ON test_runs.test_id = test_group_memberships.test_id)
  LEFT OUTER JOIN jscert.test_groups ON test_groups.id = test_group_memberships.group_id,
  jscert.test_batches,
  jscert.test_cases
WHERE
      test_runs.batch_id = test_batches.id
  AND test_runs.test_id = test_cases.id

  AND job_id = 159
  AND result <> 'PASS'
  AND (group_id > 2 OR group_id IS NULL)
--  AND chapter1 >= 8 AND chapter1 <= 14
  AND chapter1 = 15 AND chapter2 = 4
GROUP BY
  des
ORDER BY
  count desc
;
