#!/bin/sh

DIR=`dirname $0`

export PYTHONPATH=$DIR:$PYTHONPATH
export ACOUSTID_CONFIG=$DIR/acoustid.conf

$DIR/e/bin/python -m acoustid.web.app "$@"
