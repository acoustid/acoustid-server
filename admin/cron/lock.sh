#!/usr/bin/env bash

: ${VERBOSE=yes}
LOCKDIR=/var/lock/$LOCKNAME.lock

mkdir $LOCKDIR 2>/dev/null
LOCKED=$?
if [ "$LOCKED" == 1 ]; then
	PID=`cat $LOCKDIR/pid`
	if [ -d /proc/$PID ]; then
		if [ -n "$VERBOSE" ]; then
			echo "already running"
		fi
	else
		echo "stale lock for PID $PID, removing"
		rm -rf $LOCKDIR
	fi
	exit 0
fi

trap "rm -rf $LOCKDIR" EXIT
echo $$ >$LOCKDIR/pid

