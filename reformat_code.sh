#!/usr/bin/env bash

set -eu

cd $(dirname $0)

source venv/bin/activate

set -eux

isort acoustid/ tests/ 
black acoustid/ tests/
