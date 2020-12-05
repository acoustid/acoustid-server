# flake8: noqa

import gevent.monkey
gevent.monkey.patch_all()

import psycogreen
psycogreen.gevent.patch_psycopg()

from acoustid.server import make_application
application = make_application()
