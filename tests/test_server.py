# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import assert_equals
import gzip
import wsgiref.util
from cStringIO import StringIO
from acoustid.server import GzipRequestMiddleware, replace_double_slashes, add_cors_headers


def test_gzip_request_middleware():
    def app(environ, start_response):
        assert_equals('Hello world!', environ['wsgi.input'].read(int(environ['CONTENT_LENGTH'])))
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
    wsgiref.util.setup_testing_defaults(environ)
    mw = GzipRequestMiddleware(app)
    mw(environ, None)


def test_replace_double_slashes():
    def app(environ, start_response):
        assert_equals('/v2/user/lookup', environ['PATH_INFO'])
    environ = {'PATH_INFO': '/v2//user//lookup'}
    wsgiref.util.setup_testing_defaults(environ)
    mw = replace_double_slashes(app)
    mw(environ, None)


def test_add_cors_headers():
    def app(environ, start_response):
        start_response(200, [])

    def start_response(status, headers, exc_info=None):
        h = dict(headers)
        print(h)
        assert_equals(h['Access-Control-Allow-Origin'], '*')

    environ = {}
    wsgiref.util.setup_testing_defaults(environ)
    mw = add_cors_headers(app)
    mw(environ, start_response)
