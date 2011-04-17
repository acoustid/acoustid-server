#!/bin/sh

set -e

TARGET_DIR=/home/acoustid/data/`date '+%Y-%m-%d'`/

cd /home/acoustid/acoustid-server/
rm -rf /tmp/acoustid-dump/ && python admin/export-tables.py conf/acoustid.xml
cd /tmp
tar -jcvf acoustid-dump.tar.bz2 acoustid-dump
mkdir $TARGET_DIR
mv acoustid-dump.tar.bz2 $TARGET_DIR

