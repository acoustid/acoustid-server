#!/usr/bin/env bash

set -ex

cd $(dirname $0)/../../

PROJECT_DIR=$(pwd)

export COMPOSE_FILE=admin/ci/docker-compose.yml

trap "docker-compose --project-directory=$PROJECT_DIR down" EXIT

docker-compose --project-directory=$PROJECT_DIR build tests
docker-compose --project-directory=$PROJECT_DIR run tests
