#!/bin/bash
thisdir=$(readlink -f $(dirname ${BASH_SOURCE[0]})/..)
envdir=${VOLDIR:-$thisdir}/env
virtualenv --always-copy -p python2 $envdir
source $envdir/bin/activate
pip install --upgrade -r $thisdir/requirements.txt
