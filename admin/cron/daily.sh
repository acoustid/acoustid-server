#!/usr/bin/env bash

LOCKNAME=acoustid-daily
. `dirname $0`/lock.sh

DIR=`dirname $0`/../..
PSQL=$DIR/run_psql.sh
export PYTHONPATH=$DIR

$PSQL -q -t -A <$DIR/sql/CollectStats.sql | perl -pe 's{^\s+}{}'

python $DIR/scripts/update_user_agent_stats.py -q -c $DIR/acoustid.conf
python $DIR/scripts/cleanup_stats.py -q -c $DIR/acoustid.conf

