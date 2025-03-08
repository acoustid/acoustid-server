#!/usr/bin/env bash

set -eu

cd $(dirname $0)

set -eux

uv run isort acoustid/ tests/
uv run black acoustid/ tests/
