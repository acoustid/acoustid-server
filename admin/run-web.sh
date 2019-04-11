#!/usr/bin/env bash

exec uwsgi \
  --plugins python \
  --plugins ping \
  --socket 0.0.0.0:3031 \
  --chmod-socket \
  --pidfile /tmp/uwsgi-acoustid-server-web.pid \
  --master \
  --disable-logging \
  --log-date \
  --buffer-size 10240 \
  --workers 5 \
  --harakiri 30 \
  --harakiri-verbose \
  --max-requests 500 \
  --post-buffering 1 \
  --need-app \
  --virtualenv /opt/acoustid/server/venv \
  --python-path /opt/acoustid/server \
  --module acoustid.web.app:app
