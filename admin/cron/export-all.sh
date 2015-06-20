#!/usr/bin/env bash

set -e

LOCKNAME=acoustid-export
. `dirname $0`/lock.sh

DIR=`dirname $0`/../..

test -d $DIR/e && source $DIR/e/bin/activate
export PYTHONPATH=$DIR:$PYTHONPATH

TEMP_DIR=/home/acoustid/data/.export
DATA_DIR=/home/acoustid/data
TARGET_DIR=$DATA_DIR/fullexport/`date '+%Y-%m-%d'`

rm -rf $TEMP_DIR
mkdir $TEMP_DIR

if [ -e /etc/init.d/slony1 ]; then
    sudo /etc/init.d/slony1 stop
fi

$DIR/scripts/export_tables.py -q -c $DIR/acoustid.conf -d $TEMP_DIR "$@"

if [ -e /etc/init.d/slony1 ]; then
    sudo /etc/init.d/slony1 start
fi

cd $TEMP_DIR

# publish replication packets
for NAME in acoustid-update acoustid-musicbrainz-update; do
	bzip2 $NAME-*.xml
	cat ~/.gnupg/passphrase | gpg -a --batch --passphrase-fd 0 --detach-sign $NAME-*.xml.bz2
	mv $NAME-*.xml.bz2{,.asc} $DATA_DIR/replication/
done

# publish data dumps
for NAME in acoustid-dump acoustid-musicbrainz-dump; do
	if [ -d $NAME ]; then
		tar -cvf $NAME.tar.bz2 --bzip2 $NAME
		cat ~/.gnupg/passphrase | gpg -a --batch --passphrase-fd 0 --detach-sign $NAME.tar.bz2
		mkdir -p $TARGET_DIR
		mv $NAME.tar.bz2{,.asc} $TARGET_DIR
	fi
done

if [ -d acoustid-dump ]; then
	echo `basename $TARGET_DIR` >$DATA_DIR/fullexport/latest
fi

# synchronize backups
#test -x $DIR/admin/run-data-backup.sh && $DIR/admin/run-data-backup.sh

# clean up
rm -rf $TEMP_DIR

