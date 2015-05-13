select
  description,
  reason,
  count(*)
from
  jscert.fail_groups,
  jscert.fail_group_memberships
where
group_id = id and
test_id in
((
  select
    test_id
  from
    jscert.test_runs,
    jscert.test_cases,
    jscert.test_batches
  where
        test_id = test_cases.id
    and batch_id = test_batches.id
    and test_batches.job_id = 159
    and test_cases.chapter1 >=8 and test_cases.chapter1 <= 14
    and result = 'PASS'
) INTERSECT (
  select
    test_id
  from
    jscert.test_runs,
    jscert.test_cases,
    jscert.test_batches
  where
        test_id = test_cases.id
    and batch_id = test_batches.id
    and test_batches.job_id = 36
    and test_cases.chapter1 >=8 and test_cases.chapter1 <= 14
    and result <> 'PASS'
))
group by id order by count;
