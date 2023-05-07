#!/usr/bin/env bash

cd /opt/acoustid/server
export PYTHONPATH="$PWD"
exec /opt/acoustid/server.venv/bin/alembic "$@"
