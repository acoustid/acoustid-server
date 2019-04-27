#!/usr/bin/env bash

set -ex

cd $(dirname $0)

docker-compose build tests
docker-compose run tests

docker-compose down
