#!/usr/bin/env bash

ADMINDIR=`dirname $0`/../
PSQL=$ADMINDIR/psql.sh

$PSQL -q <$ADMINDIR/sql/CollectStats.sql

