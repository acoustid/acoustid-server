# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import gzip
import wsgiref.util
from typing import TYPE_CHECKING, Any, Callable, List, Tuple

from six import BytesIO

from acoustid.server import (
    GzipRequestMiddleware,
    add_cors_headers,
    replace_double_slashes,
)

if TYPE_CHECKING:
    from wsgiref.types import WSGIEnvironment


def dummy_start_response(status, headers, exc_info=None):
    # type: (str, List[Tuple[str, str]], Any) -> Callable[[bytes], None]
    def write(x):
        pass

    return write


def test_gzip_request_middleware():
    # type: () -> None
    def app(environ, start_response):
        assert environ["wsgi.input"].read() == b"Hello world!"

    gzcontent = BytesIO()
    f = gzip.GzipFile(fileobj=gzcontent, mode="w")
    f.write(b"Hello world!")
    f.close()
    data = gzcontent.getvalue()
    environ = {
        "HTTP_CONTENT_ENCODING": "gzip",
        "CONTENT_LENGTH": str(len(data)),
        "wsgi.input": BytesIO(data),
    }
    wsgiref.util.setup_testing_defaults(environ)
    mw = GzipRequestMiddleware(app)
    mw(environ, dummy_start_response)


def test_gzip_request_middleware_invalid_gzip():
    # type: () -> None
    def app(environ, start_response):
        assert environ["wsgi.input"].read() == b"Hello world!"

    data = b"Hello world!"
    environ = {
        "HTTP_CONTENT_ENCODING": "gzip",
        "CONTENT_LENGTH": str(len(data)),
        "wsgi.input": BytesIO(data),
    }
    wsgiref.util.setup_testing_defaults(environ)
    mw = GzipRequestMiddleware(app)
    mw(environ, dummy_start_response)


def test_replace_double_slashes():
    # type: () -> None
    def app(environ, start_response):
        assert environ["PATH_INFO"] == "/v2/user/lookup"

    environ = {"PATH_INFO": "/v2//user//lookup"}
    wsgiref.util.setup_testing_defaults(environ)
    mw = replace_double_slashes(app)
    mw(environ, dummy_start_response)


def test_add_cors_headers():
    # type: () -> None
    def app(environ, start_response):
        start_response(200, [])

    def start_response(status, headers, exc_info=None):
        # type: (str, List[Tuple[str, str]], Any) -> Callable[[bytes], None]
        h = dict(headers)
        print(h)
        assert h["Access-Control-Allow-Origin"] == "*"
        return dummy_start_response(status, headers, exc_info=exc_info)

    environ = {}  # type: WSGIEnvironment
    wsgiref.util.setup_testing_defaults(environ)
    mw = add_cors_headers(app)
    mw(environ, start_response)
