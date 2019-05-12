# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

# Simple WSGI module intended to be used by uWSGI, e.g.:
# uwsgi -w acoustid.wsgi --pythonpath ~/acoustid/ --env ACOUSTID_CONFIG=~/acoustid/acoustid.conf --http :9090
# uwsgi -w acoustid.wsgi --pythonpath ~/acoustid/ --env ACOUSTID_CONFIG=~/acoustid/acoustid.conf -M -L --socket 127.0.0.1:1717

import os
try:
    import uwsgi
except ImportError:
    uwsgi = None

from acoustid.server import make_application  # noqa: E402
server, application = make_application(os.environ['ACOUSTID_CONFIG'])

if uwsgi is not None:
    uwsgi.atexit = server.atexit
