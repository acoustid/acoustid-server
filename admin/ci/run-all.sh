#!/usr/bin/env bash

set -ex

cd $(dirname $0)/../../

export COMPOSE_FILE=admin/ci/docker-compose.yml

trap 'docker-compose down' EXIT

docker-compose build tests
docker-compose run tests
