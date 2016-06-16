#!/bin/sh
export VOLDIR=/vol/rr/gitlab-builds/${1:?}/$CI_BUILD_ID
mkdir -p $VOLDIR
