#!/usr/bin/env bash

LOCKNAME=acoustid-daily
. `dirname $0`/lock.sh

DIR=`dirname $0`/../..
export PYTHONPATH=$DIR

python $DIR/scripts/update_stats.py -q -c $DIR/acoustid.conf
python $DIR/scripts/update_user_agent_stats.py -q -c $DIR/acoustid.conf
python $DIR/scripts/cleanup_perf_stats.py -q -c $DIR/acoustid.conf

