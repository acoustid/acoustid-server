#!/usr/bin/env bash

set -ex

/wait-for-it.sh $ACOUSTID_TEST_REDIS_HOST:6379
/wait-for-it.sh $ACOUSTID_TEST_POSTGRES_HOST:5432

#source /etc/os-release
#export PIP_CACHE_DIR=/cache/pip-$ID-$VERSION_ID-$(uname -m)

cd /build/acoustid-server
tox --recreate
