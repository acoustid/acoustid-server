# flake8: noqa

# Patching has to happen before anything else is imported, so that the
# standard library the app then imports is already the cooperative version.
# psycopg2 is a C extension and gevent cannot see into it, so psycogreen is
# what stops a query blocking the whole worker rather than one greenlet.
import gevent.monkey

gevent.monkey.patch_all()

import psycogreen.gevent

psycogreen.gevent.patch_psycopg()

from acoustid.web.app import make_application

application = make_application()
