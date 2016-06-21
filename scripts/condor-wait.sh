#!/bin/bash
source condor.jobinfo

count=1
until (($count > 40)) || condor_wait -wait 60 $RUNTESTS_CONDOR_LOG; do
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
