#!/usr/bin/env bash

set -e

ADMINDIR=`dirname $0`
eval `$ADMINDIR/dumpconfig.py $ADMINDIR/../conf/acoustid.xml`

opts="-U $DB_USER -h $DB_HOST"
if [ "x$DB_PORT" != "x" ]; then
	opts+=" -p $DB_PORT"
fi
psql $opts $DB_NAME "$@"

