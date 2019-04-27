#!/usr/bin/env bash

set -e

LOCKNAME=acoustid-musicbrainz
. `dirname $0`/lock.sh

DIR=`dirname $0`/../..

test -d $DIR/e && source $DIR/e/bin/activate
export PYTHONPATH=$DIR:$PYTHONPATH

# update the MusicBrainz database
test -x $DIR/admin/run-mbslave.sh && $DIR/admin/run-mbslave.sh

# fix merged MBIDs
# $DIR/scripts/merge_missing_mbids.py -q -c $DIR/acoustid.conf
