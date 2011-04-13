#!/usr/bin/env python

import os
import logging
from wsgiref.simple_server import make_server
from acoustid.server import make_application

logging.basicConfig(level=logging.DEBUG)

config_path = os.path.dirname(os.path.abspath(__file__)) + '/../acoustid.conf'
application = make_application(config_path)

host = 'localhost'
port = 8080

server = make_server(host, port, application)
print 'Listening on http://%s:%s/ ...' % (host, port)
server.serve_forever()

