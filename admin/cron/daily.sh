#!/usr/bin/env bash

LOCKNAME=acoustid-daily
. `dirname $0`/lock.sh

DIR=`dirname $0`/../..
PSQL=$DIR/run_psql.sh

$PSQL -q -t -A <$DIR/sql/CollectStats.sql | perl -pe 's{^\s+}{}'

