#!/usr/bin/env bash

LOCKNAME=acoustid-import
. `dirname $0`/lock.sh

DIR=`dirname $0`/../..

PYTHONPATH=$DIR $DIR/scripts/import_queued_submissions.py -q -c $DIR/acoustid.conf
PYTHONPATH=$DIR $DIR/scripts/update_index.py -q -c $DIR/acoustid.conf

