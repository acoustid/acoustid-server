#!/bin/sh

set -e

DIR=/home/acoustid/acoustid-server/

TARGET_DIR=/home/acoustid/data/`date '+%Y-%m-%d'`/

cd $DIR
rm -rf /tmp/acoustid-dump/ && PYTHONPATH=$DIR python scripts/export_tables.py -c acoustid.conf
cd /tmp
tar -jcvf acoustid-dump.tar.bz2 acoustid-dump
mkdir -p $TARGET_DIR
mv acoustid-dump.tar.bz2 $TARGET_DIR

