#!/usr/bin/env bash

set -e

LOCKNAME=acoustid-hourly
. `dirname $0`/lock.sh

DIR=`dirname $0`/../..
export PYTHONPATH=$DIR

if [ "$1" != "--slave" ]; then
	python $DIR/scripts/update_lookup_stats.py -q -c $DIR/acoustid.conf
fi

python $DIR/scripts/cleanup_stats.py -q -c $DIR/acoustid.conf

