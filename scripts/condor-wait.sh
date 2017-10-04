#!/bin/bash
source condor.jobinfo

# 40 minutes default timeout, or passed as the first parameter
timeout=${1:-40}
count=1
until (($count > $timeout)) || (condor_wait -wait 60 $RUNTESTS_CONDOR_LOG > >(grep -v "Time expired.")); do
  echo -n "${count} minute elapsed: "
  condor_q -userlog $RUNTESTS_CONDOR_LOG | tail -1
  held_jobs=$(condor_q -userlog $RUNTESTS_CONDOR_LOG -constraint JobStatus==5 -format "%d\n" JobStatus | wc -l)
  if (($held_jobs)); then
    echo "Detected $held_jobs held jobs:"
    condor_q -userlog $RUNTESTS_CONDOR_LOG -constraint JobStatus==5 -format "%d." ClusterId -format "%d: " ProcId -format "%s\n" HoldReason
    condor_release $RUNTESTS_CONDOR_ID
  fi
  ((count++))
done

# Clean-up the rest, as we've given up (timeout failed?)
if (($count > $timeout)); then
  echo "Timed out, removing remaining jobs:"
  condor_status $RUNTESTS_CONDOR_ID
  condor_rm $RUNTESTS_CONDOR_ID
  exit 1
fi
# TODO: Output an error message detailing how to restart these tasks manually
