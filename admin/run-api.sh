#!/usr/bin/env bash

exec /opt/acoustid/server.venv/bin/uwsgi \
  --plugins python \
  --plugins ping \
  --http-socket 0.0.0.0:3031 \
  --chmod-socket \
  --pidfile /tmp/uwsgi-acoustid-server-api.pid \
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
  --virtualenv /opt/acoustid/server.venv \
  --python-path /opt/acoustid/server \
  --module acoustid.wsgi
