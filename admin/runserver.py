#!/usr/bin/env python

import os
import logging
from wsgiref.simple_server import make_server
from acoustid import Server

logging.basicConfig(level=logging.DEBUG)

config_path = os.path.dirname(os.path.abspath(__file__)) + '/../acoustid.conf'
application = Server(config_path)

for logger_name, level in sorted(application.config.logging.levels.items()):
    logging.getLogger(logger_name).setLevel(level)

host = 'localhost'
port = 8080

server = make_server(host, port, application)
print 'Listening on http://%s:%s/ ...' % (host, port)
server.serve_forever()

