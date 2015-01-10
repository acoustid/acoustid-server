#!//usr/bin/env bash

DIR=$(dirname $(readlink $0))/../..
NAME=$(basename $0 | sed s/acoustid_//)

test -d $DIR/e && source $DIR/e/bin/activate
export PYTHONPATH=$DIR:$PYTHONPATH

python $DIR/scripts/munin_$NAME.py -q -c $DIR/acoustid.conf "$@"

