# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

from nose.tools import *
import gzip
from cStringIO import StringIO
from acoustid.server import GzipRequestMiddleware


def test_gzip_request_middleware():
    def app(environ, start_response):
        assert_equal('Hello world!', environ['wsgi.input'].read(int(environ['CONTENT_LENGTH'])))
    gzcontent = StringIO()
    f = gzip.GzipFile(fileobj=gzcontent, mode='w')
    f.write('Hello world!')
    f.close()
    data = gzcontent.getvalue()
    environ = {
        'HTTP_CONTENT_ENCODING': 'gzip',
        'CONTENT_LENGTH': len(data),
        'wsgi.input': StringIO(data),
    }
    mw = GzipRequestMiddleware(app)
    mw(environ, None)

