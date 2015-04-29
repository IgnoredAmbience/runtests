SELECT 
  test_runs.test_id, 
  test_runs.result, 
  test_runs.exit_code, 
  test_runs.stdout, 
  test_runs.stderr, 
  test_runs.duration, 
  test_batches.system, 
  test_batches.start_time, 
  test_batches.condor_proc
FROM 
  jscert.test_batches, 
  jscert.test_runs
WHERE 
  test_runs.batch_id = test_batches.id AND
  test_batches.job_id = 16 /*AND
  test_runs.result = 'UNKNOWN'*/;
