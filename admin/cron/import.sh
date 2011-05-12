#!/usr/bin/env bash

LOCKNAME=acoustid-import
. `dirname $0`/lock.sh

DIR=`dirname $0`/../..

PYTHONPATH=$DIR $DIR/scripts/import_queued_submissions.py -q -c $DIR/acoustid.conf

