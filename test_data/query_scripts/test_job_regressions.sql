SELECT 
  new_runs.test_id, 
  old_runs.result old_result, 
  old_runs.exit_code old_exit_code, 
  old_runs.stdout old_stdout, 
  old_runs.stderr old_stderr, 
  old_runs.duration old_duration,
  new_runs.result new_result, 
  new_runs.exit_code new_exit_code, 
  new_runs.stdout new_stdout, 
  new_runs.stderr new_stderr, 
  new_runs.duration new_duration
FROM 
  jscert.test_runs old_runs, 
  jscert.test_batches old_batch, 
  jscert.test_runs new_runs, 
  jscert.test_batches new_batch
WHERE 
  old_runs.batch_id = old_batch.id AND
  new_runs.test_id = old_runs.test_id AND
  new_runs.batch_id = new_batch.id AND
  old_batch.job_id = 129 AND
  new_batch.job_id = 117 AND
  new_runs.result != old_runs.result /*AND
  old_runs.result = 'PASS'*/;
