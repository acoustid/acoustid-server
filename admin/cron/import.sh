#!/usr/bin/env bash

LOCKNAME=acoustid-import
. `dirname $0`/lock.sh

DIR=`dirname $0`/../..

if [ "$1" != "--slave" ]; then
       PYTHONPATH=$DIR $DIR/scripts/import_queued_submissions.py -q -c $DIR/acoustid.conf
fi

PYTHONPATH=$DIR $DIR/scripts/update_index.py -q -c $DIR/acoustid.conf

