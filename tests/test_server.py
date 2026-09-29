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


def capture_status():
    # type: () -> Tuple[List[str], Callable[..., Callable[[bytes], None]]]
    """A start_response that records the status line the middleware sends."""
    seen = []  # type: List[str]

    def start_response(status, headers, exc_info=None):
        # type: (str, List[Tuple[str, str]], Any) -> Callable[[bytes], None]
        seen.append(status)

        def write(x):
            # type: (bytes) -> None
            pass

        return write

    return seen, start_response


def run_gzip_middleware(data):
    # type: (bytes) -> Tuple[List[str], List[bytes]]
    """Feed a body to the middleware and report the status and what got through."""
    delivered = []  # type: List[bytes]

    def app(environ, start_response):
        # type: (Any, Any) -> List[bytes]
        delivered.append(environ["wsgi.input"].read())
        return []

    environ = {
        "HTTP_CONTENT_ENCODING": "gzip",
        "CONTENT_LENGTH": str(len(data)),
        "wsgi.input": BytesIO(data),
    }
    wsgiref.util.setup_testing_defaults(environ)
    seen, start_response = capture_status()
    GzipRequestMiddleware(app)(environ, start_response)
    return seen, delivered


def gzipped(payload):
    # type: (bytes) -> bytes
    buf = BytesIO()
    f = gzip.GzipFile(fileobj=buf, mode="w")
    f.write(payload)
    f.close()
    return buf.getvalue()


def test_gzip_request_middleware_answers_400_for_a_truncated_body():
    # type: () -> None
    """A client that gave up mid-upload raises EOFError, which is not an
    OSError, so it used to escape as a 500."""
    data = gzipped(b"Hello world!" * 100)
    seen, delivered = run_gzip_middleware(data[: len(data) // 2])
    assert seen == ["400 BAD REQUEST"]
    assert delivered == []


def test_gzip_request_middleware_answers_400_for_a_corrupt_payload():
    # type: () -> None
    """A valid header over a corrupt deflate stream raises zlib.error, which is
    also not an OSError."""
    data = gzipped(b"Hello world!" * 100)
    seen, delivered = run_gzip_middleware(data[:10] + b"\x00" * 200)
    assert seen == ["400 BAD REQUEST"]
    assert delivered == []


def test_gzip_request_middleware_answers_400_for_a_body_that_is_not_gzip():
    # type: () -> None
    seen, delivered = run_gzip_middleware(b"Hello world!")
    assert seen == ["400 BAD REQUEST"]
    assert delivered == []


def test_gzip_request_middleware_still_passes_a_valid_body_through():
    # type: () -> None
    seen, delivered = run_gzip_middleware(gzipped(b"Hello world!"))
    assert seen == []
    assert delivered == [b"Hello world!"]
