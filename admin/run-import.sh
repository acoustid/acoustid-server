#!/usr/bin/env bash

export PYTHONPATH="/opt/acoustid/server"
exec /opt/acoustid/server/venv/bin/python /opt/acoustid/server/scripts/import_submissions.py -q -c "$ACOUSTID_CONFIG"
