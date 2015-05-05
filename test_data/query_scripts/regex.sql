insert into jscert.test_group_memberships (group_id, test_id)
select 26, test_id
from
  jscert.test_runs,
  jscert.test_batches,
  jscert.test_cases
where
  test_runs.batch_id = test_batches.id and
  test_runs.test_id = test_cases.id and
  test_cases.chapter1 = 15 and test_cases.chapter2 = 4 and
  test_runs.result <> 'PASS' and
  test_batches.job_id = 155 and

  /*test_runs.stdout ~ 'Translation of Javascript syntax does not support `\['*/
  /*test_runs.stdout ~ 'Translation of Javascript syntax does not support `for\s*\([^)]* in '*/
  /*test_runs.stdout ~ 'NYI:  this is not implemented yet!'*/
  test_runs.stderr ~ 'Fatal error: exception Parser.InvalidArgument'

;
