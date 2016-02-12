#!/usr/bin/env python

import os
import logging
from werkzeug.serving import run_simple
from acoustid.server import make_application

logging.basicConfig(level=logging.DEBUG)

config_path = os.path.dirname(os.path.abspath(__file__)) + '/../acoustid.conf'
application = make_application(config_path)

# server static files
static_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static'))
static_files = {
    '/favicon.ico': os.path.join(static_path, 'favicon.ico'),
    '/static': static_path,
}

host = '0.0.0.0'
port = 5000

run_simple(host, port, application, use_reloader=True, static_files=static_files, processes=5)

