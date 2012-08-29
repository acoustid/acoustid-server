#!/bin/sh

DIR=`dirname $0`/..
export PYTHONPATH=${DIR}
${DIR}/scripts/acoustid_sync.py -c ${DIR}/acoustid.conf
exit $?

