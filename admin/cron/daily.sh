#!/usr/bin/env bash

ROOTDIR=`dirname $0`/../../
PSQL=$ROOTDIR/run_psql.sh

$PSQL <$ROOTDIR/sql/CollectStats.sql

