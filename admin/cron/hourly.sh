#!/usr/bin/env bash

set -e

LOCKNAME=acoustid-hourly
. `dirname $0`/lock.sh

DIR=`dirname $0`/../..
export PYTHONPATH=$DIR

# randomize the time this script starts at a little
sleep $(( $RANDOM % 60 ))

python $DIR/scripts/update_lookup_stats.py -q -c $DIR/acoustid.conf

