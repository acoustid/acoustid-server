#!/usr/bin/env bash
exec uwsgi \
  --plugins python \
  --plugins ping \
  --socket 0.0.0.0:3031 \
  --socket /var/run/acoustid/uwsgi-acoustid-server-api.sock \
  --chmod-socket \
  --pidfile /var/run/acoustid/uwsgi-acoustid-server-api.pid \
  --master \
  --disable-logging \
  --log-date \
  --buffer-size 10240 \
  --workers 20 \
  --harakiri 30 \
  --harakiri-verbose \
  --max-requests 500 \
  --post-buffering 1 \
  --virtualenv /opt/acoustid/server/venv \
  --python-path /opt/acoustid/server \
  --module acoustid.wsgi