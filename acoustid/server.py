# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from __future__ import annotations

import gzip
import os
from typing import TYPE_CHECKING, Any, Callable, Iterable, List, Optional, Tuple

from six import BytesIO
from werkzeug.exceptions import BadRequest, ClientDisconnected, HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.routing import Map, Rule, RuleFactory, Submount
from werkzeug.wrappers import Request
from werkzeug.wsgi import get_content_length, get_input_stream

import acoustid.api.v1
import acoustid.api.v2
import acoustid.api.v2.internal
import acoustid.api.v2.misc
from acoustid._release import GIT_RELEASE
from acoustid.script import Script

if TYPE_CHECKING:
    from _typeshed.wsgi import StartResponse, WSGIApplication, WSGIEnvironment


endpoints = {
    "health": acoustid.api.HealthHandler,
    "health_ro": acoustid.api.ReadOnlyHealthHandler,
    "health_docker": acoustid.api.ReadOnlyHealthHandler,
    "v1.lookup": acoustid.api.v1.LookupHandler,
    "v1.submit": acoustid.api.v1.SubmitHandler,
    "v2.lookup": acoustid.api.v2.LookupHandler,
    "v2.submit": acoustid.api.v2.SubmitHandler,
    "v2.submission_status": acoustid.api.v2.SubmissionStatusHandler,
    "v2.fingerprint": acoustid.api.v2.misc.GetFingerprintHandler,
    "v2.track.list_by_mbid": acoustid.api.v2.misc.TrackListByMBIDHandler,
    "v2.track.list_by_puid": acoustid.api.v2.misc.TrackListByPUIDHandler,
    "v2.user.lookup": acoustid.api.v2.misc.UserLookupHandler,
    "v2.user.create_anonymous": acoustid.api.v2.misc.UserCreateAnonymousHandler,
    "v2.user.create_musicbrainz": acoustid.api.v2.misc.UserCreateMusicBrainzHandler,
    "v2.internal.update_lookup_stats": acoustid.api.v2.internal.UpdateLookupStatsHandler,
    "v2.internal.update_user_agent_stats": acoustid.api.v2.internal.UpdateUserAgentStatsHandler,
    "v2.internal.lookup_stats": acoustid.api.v2.internal.LookupStatsHandler,
    "v2.internal.create_account": acoustid.api.v2.internal.CreateAccountHandler,
    "v2.internal.create_application": acoustid.api.v2.internal.CreateApplicationHandler,
    "v2.internal.update_application_status": acoustid.api.v2.internal.UpdateApplicationStatusHandler,
    "v2.internal.check_application": acoustid.api.v2.internal.CheckApplicationHandler,
}


api_url_rules = [
    Rule("/_health", endpoint="health"),
    Rule("/_health_ro", endpoint="health_ro"),
    Rule("/_health_docker", endpoint="health_docker"),
    Rule("/lookup", endpoint="v1.lookup"),
    Rule("/submit", endpoint="v1.submit"),
    Submount(
        "/v2",
        [
            Rule("/lookup", endpoint="v2.lookup"),
            Rule("/submit", endpoint="v2.submit"),
            Rule("/submission_status", endpoint="v2.submission_status"),
            Rule("/fingerprint", endpoint="v2.fingerprint"),
            Rule("/track/list_by_mbid", endpoint="v2.track.list_by_mbid"),
            Rule("/track/list_by_puid", endpoint="v2.track.list_by_puid"),
            Rule("/user/lookup", endpoint="v2.user.lookup"),
            Rule("/user/create_anonymous", endpoint="v2.user.create_anonymous"),
            Rule("/user/create_musicbrainz", endpoint="v2.user.create_musicbrainz"),
            Submount(
                "/internal",
                [
                    Rule(
                        "/update_lookup_stats",
                        endpoint="v2.internal.update_lookup_stats",
                    ),
                    Rule(
                        "/update_user_agent_stats",
                        endpoint="v2.internal.update_user_agent_stats",
                    ),
                    Rule("/lookup_stats", endpoint="v2.internal.lookup_stats"),
                    Rule("/create_account", endpoint="v2.internal.create_account"),
                    Rule(
                        "/create_application", endpoint="v2.internal.create_application"
                    ),
                    Rule(
                        "/update_application_status",
                        endpoint="v2.internal.update_application_status",
                    ),
                    Rule(
                        "/check_application", endpoint="v2.internal.check_application"
                    ),
                ],
            ),
        ],
    ),
]  # type: List[RuleFactory]


MAX_CONTENT_LENGTH = 1024 * 1024
MAX_FORM_PARTS = 1000
MAX_FORM_MEMORY_SIZE = 1024 * 1024


class Server(Script):
    def __init__(self, config_path: str) -> None:
        super(Server, self).__init__(config_path)
        url_rules = api_url_rules
        self.url_map = Map(url_rules, strict_slashes=False)

    def __call__(
        self, environ: WSGIEnvironment, start_response: StartResponse
    ) -> Iterable[bytes]:
        return self.wsgi_app(environ, start_response)

    def wsgi_app(
        self, environ: WSGIEnvironment, start_response: StartResponse
    ) -> Iterable[bytes]:
        urls = self.url_map.bind_to_environ(environ)
        try:
            endpoint, args = urls.match()
            handler_class = endpoints.get(endpoint)
            if handler_class is None:
                raise BadRequest("Unknown endpoint")
            with self.context() as ctx:
                handler = handler_class(ctx, **args)
                request = Request(environ)
                request.max_content_length = MAX_CONTENT_LENGTH
                request.max_form_parts = MAX_FORM_PARTS
                request.max_form_memory_size = MAX_FORM_MEMORY_SIZE
                response = handler.handle(request)
        except HTTPException as e:
            return e(environ, start_response)
        return response(environ, start_response)


class GzipRequestMiddleware(object):
    """WSGI middleware to handle GZip-compressed HTTP requests bodies

    :param app: a WSGI application
    """

    def __init__(self, app):
        # type: (WSGIApplication) -> None
        self.app = app

    def __call__(self, environ, start_response):
        # type: (WSGIEnvironment, StartResponse) -> Iterable[bytes]
        content_encoding = environ.get("HTTP_CONTENT_ENCODING", "").lower().strip()
        if content_encoding == "gzip":
            content_length = get_content_length(environ)
            if content_length is not None:
                if content_length > MAX_CONTENT_LENGTH:
                    bad_request = BadRequest("Request body is too large")
                    return bad_request(environ, start_response)
            try:
                compressed_body = get_input_stream(environ).read()
            except ClientDisconnected:
                bad_request = BadRequest()
                return bad_request(environ, start_response)
            try:
                body = gzip.GzipFile(fileobj=BytesIO(compressed_body)).read()
            except IOError:
                bad_request = BadRequest()
                return bad_request(environ, start_response)
            environ["wsgi.input"] = BytesIO(body)
            environ["CONTENT_LENGTH"] = str(len(body))
            del environ["HTTP_CONTENT_ENCODING"]
        return self.app(environ, start_response)


def replace_double_slashes(app):
    # type: (WSGIApplication) -> WSGIApplication
    def wrapped_app(environ, start_response):
        # type: (WSGIEnvironment, StartResponse) -> Iterable[bytes]
        environ["PATH_INFO"] = environ["PATH_INFO"].replace("//", "/")
        return app(environ, start_response)

    return wrapped_app


def add_cors_headers(app: WSGIApplication) -> WSGIApplication:
    def wrapped_app(
        environ: WSGIEnvironment, start_response: StartResponse
    ) -> Iterable[bytes]:
        def start_response_with_cors_headers(
            status: str, headers: List[Tuple[str, str]], exc_info: Optional[Any] = None
        ) -> Callable[[bytes], object]:
            headers.append(("Access-Control-Allow-Origin", "*"))
            return start_response(status, headers, exc_info)

        return app(environ, start_response_with_cors_headers)

    return wrapped_app


def make_application(config_path=None):
    # type: (Optional[str]) -> Server
    """Construct a WSGI application for the AcoustID server

    :param config_path: path to the server configuration file
    """
    if config_path is None:
        config_path = os.environ.get("ACOUSTID_CONFIG", "")
    assert config_path is not None
    server = Server(config_path)
    server.wsgi_app = GzipRequestMiddleware(server.wsgi_app)  # type: ignore
    server.wsgi_app = replace_double_slashes(server.wsgi_app)  # type: ignore
    server.wsgi_app = add_cors_headers(server.wsgi_app)  # type: ignore
    server.wsgi_app = ProxyFix(server.wsgi_app)  # type: ignore
    return server
