# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

# Simple WSGI module intended to be used by uWSGI, e.g.:
# uwsgi -w acoustid.wsgi --pythonpath ~/acoustid/ --env ACOUSTID_CONFIG=~/acoustid/acoustid.conf --http :9090
# uwsgi -w acoustid.wsgi --pythonpath ~/acoustid/ --env ACOUSTID_CONFIG=~/acoustid/acoustid.conf -M -L --socket 127.0.0.1:1717

import os
import sys
try:
    import uwsgi
except ImportError:
    uwsgi = None

base_dir = os.path.join(os.path.dirname(__file__), '..')

activate_this = os.path.join(base_dir, 'e', 'bin', 'activate_this.py')
if os.path.exists(activate_this):
    execfile(activate_this, dict(__file__=activate_this))

sys.path.insert(0, base_dir)

from acoustid.server import make_application  # noqa: E402
server, application = make_application(os.environ['ACOUSTID_CONFIG'])

if uwsgi is not None:
    uwsgi.atexit = server.atexit
