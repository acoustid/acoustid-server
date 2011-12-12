#!/bin/sh

DIR=`dirname $0`
PYTHONPATH=$DIR:$PYTHONPATH $DIR/scripts/run_psql.py -c $DIR/acoustid.conf -q -- "$@"

