#!/usr/bin/env bash

set -e

LOCKNAME=acoustid-hourly
. `dirname $0`/lock.sh

DIR=`dirname $0`/../..

test -d $DIR/e && source $DIR/e/bin/activate
export PYTHONPATH=$DIR:$PYTHONPATH

# randomize the time this script starts at a little
sleep $(( $RANDOM % 60 ))

python $DIR/scripts/update_lookup_stats.py -q -c $DIR/acoustid.conf

