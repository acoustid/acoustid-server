#!/usr/bin/env bash

LOCKNAME=acoustid-daily
. `dirname $0`/lock.sh

DIR=`dirname $0`/../..
PSQL=$DIR/run_psql.sh

$PSQL <$DIR/sql/CollectStats.sql

