#!/bin/bash
dir=${VOLDIR:-.}
virtualenv --always-copy -p python2 $dir/pyenv
source $dir/pyenv/bin/activate
pip install --upgrade -r $dir/requirements.txt
