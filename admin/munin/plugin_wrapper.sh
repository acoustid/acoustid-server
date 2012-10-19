#!//usr/bin/env bash

dir=$(dirname $(readlink $0))/../..
name=$(basename $0 | sed s/acoustid_//)

export PYTHONPATH=$dir
python $dir/scripts/munin_$name.py -q -c $dir/acoustid.conf "$@"

