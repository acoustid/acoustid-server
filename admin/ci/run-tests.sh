#!/usr/bin/env bash

set -ex

/wait-for-it.sh $ACOUSTID_TEST_INDEX_HOST:6080
/wait-for-it.sh $ACOUSTID_TEST_REDIS_HOST:6379
/wait-for-it.sh $ACOUSTID_TEST_DATABASE_APP_HOST:5432
/wait-for-it.sh $ACOUSTID_TEST_DATABASE_FINGERPRINT_HOST:5432
/wait-for-it.sh $ACOUSTID_TEST_DATABASE_INGEST_HOST:5432
/wait-for-it.sh $ACOUSTID_TEST_DATABASE_MUSICBRAINZ_HOST:5432

export PIP_CACHE_DIR=`pwd`/pip-cache

ls -l
tox --recreate
