#!/bin/sh -x
rm -Rf /vol/rr/gitlab-builds/${1:?}/$CI_BUILD_ID
