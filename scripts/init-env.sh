#!/bin/bash
dir=$(readlink -f $(dirname ${BASH_SOURCE[0]})/..)
virtualenv -p python2 $dir/env
source $dir/env/bin/activate
pip install --upgrade -r $dir/requirements.txt

if [ -d $VOLDIR ]; then
  virtualenv-clone env $VOLDIR/env
  deactivate
  source $VOLDIR/env/bin/activate
fi
