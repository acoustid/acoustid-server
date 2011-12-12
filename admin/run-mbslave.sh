#!/bin/sh

set -e

echo >>/var/log/acoustid/mbslave.log
date >>/var/log/acoustid/mbslave.log
/home/acoustid/mbslave/mbslave-sync.py >>/var/log/acoustid/mbslave.log

