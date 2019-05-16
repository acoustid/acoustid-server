#!/usr/bin/env bash

exec /opt/acoustid/server.venv/bin/uwsgi \
  --http-socket 0.0.0.0:3032 \
  --chmod-socket \
  --pidfile /tmp/uwsgi-acoustid-server-web.pid \
  --master \
  --disable-logging \
  --log-date \
  --buffer-size 10240 \
  --workers 4 \
  --offload-threads 1 \
  --harakiri 60 \
  --harakiri-verbose \
  --post-buffering 1 \
  --enable-threads \
  --need-app \
  --static-map /static=/opt/acoustid/server/acoustid/web/static \
  --static-map /favicon.ico=/opt/acoustid/server/acoustid/web/static/favicon.ico \
  --static-map /robots.txt=/opt/acoustid/server/acoustid/web/static/robots.txt \
  --virtualenv /opt/acoustid/server.venv \
  --python-path /opt/acoustid/server \
  --module 'acoustid.web.app:make_application()'
