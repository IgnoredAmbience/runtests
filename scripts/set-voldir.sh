#!/bin/sh -x
set -x
export VOLDIR=/vol/rr/gitlab-builds/${1:?}/$CI_BUILD_ID
mkdir -p $VOLDIR
set +x
