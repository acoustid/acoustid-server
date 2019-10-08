# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import gzip
import sentry_sdk
from typing import Callable, List, Tuple, Any, Iterable, Optional, TYPE_CHECKING
from werkzeug.wsgi import get_input_stream
from sentry_sdk.integrations.wsgi import SentryWsgiMiddleware
from six import BytesIO
from werkzeug.exceptions import HTTPException
from werkzeug.routing import Map, Rule, Submount, RuleFactory
from werkzeug.wrappers import Request
from werkzeug.middleware.proxy_fix import ProxyFix
from acoustid.script import Script
from acoustid._release import GIT_RELEASE
import acoustid.api.v1
import acoustid.api.v2
import acoustid.api.v2.misc
import acoustid.api.v2.internal

if TYPE_CHECKING:
    from wsgiref.types import WSGIApplication, WSGIEnvironment, StartResponse


api_url_rules = [
    Rule('/_health', endpoint=acoustid.api.HealthHandler),
    Rule('/_health_ro', endpoint=acoustid.api.ReadOnlyHealthHandler),
    Rule('/_health_docker', endpoint=acoustid.api.ReadOnlyHealthHandler),
    Rule('/lookup', endpoint=acoustid.api.v1.LookupHandler),
    Rule('/submit', endpoint=acoustid.api.v1.SubmitHandler),
    Submount('/v2', [
        Rule('/lookup', endpoint=acoustid.api.v2.LookupHandler),
        Rule('/submit', endpoint=acoustid.api.v2.SubmitHandler),
        Rule('/submission_status', endpoint=acoustid.api.v2.SubmissionStatusHandler),
        Rule('/fingerprint', endpoint=acoustid.api.v2.misc.GetFingerprintHandler),
        Rule('/track/list_by_mbid', endpoint=acoustid.api.v2.misc.TrackListByMBIDHandler),
        Rule('/track/list_by_puid', endpoint=acoustid.api.v2.misc.TrackListByPUIDHandler),
        Rule('/user/lookup', endpoint=acoustid.api.v2.misc.UserLookupHandler),
        Rule('/user/create_anonymous', endpoint=acoustid.api.v2.misc.UserCreateAnonymousHandler),
        Rule('/user/create_musicbrainz', endpoint=acoustid.api.v2.misc.UserCreateMusicBrainzHandler),
        Submount('/internal', [
            Rule('/update_lookup_stats', endpoint=acoustid.api.v2.internal.UpdateLookupStatsHandler),
            Rule('/update_user_agent_stats', endpoint=acoustid.api.v2.internal.UpdateUserAgentStatsHandler),
            Rule('/lookup_stats', endpoint=acoustid.api.v2.internal.LookupStatsHandler),
            Rule('/create_account', endpoint=acoustid.api.v2.internal.CreateAccountHandler),
            Rule('/create_application', endpoint=acoustid.api.v2.internal.CreateApplicationHandler),
            Rule('/update_application_status', endpoint=acoustid.api.v2.internal.UpdateApplicationStatusHandler),
        ]),
    ]),
]  # type: List[RuleFactory]

admin_url_rules = [
    Submount('/admin', [
    ])
]  # type: List[RuleFactory]


class Server(Script):

    def __init__(self, config_path):
        # type: (str) -> None
        super(Server, self).__init__(config_path)
        url_rules = api_url_rules + admin_url_rules
        self.url_map = Map(url_rules, strict_slashes=False)

    def __call__(self, environ, start_response):
        # type: (WSGIEnvironment, StartResponse) -> Iterable[bytes]
        urls = self.url_map.bind_to_environ(environ)
        try:
            handler_class, args = urls.match()
            with self.context() as ctx:
                handler = handler_class(ctx, **args)
                response = handler.handle(Request(environ))
        except HTTPException as e:
            return e(environ, start_response)
        return response(environ, start_response)

    def setup_sentry(self):
        # type: () -> None
        sentry_sdk.init(self.config.sentry.api_dsn, release=GIT_RELEASE)


class GzipRequestMiddleware(object):
    """WSGI middleware to handle GZip-compressed HTTP requests bodies

    :param app: a WSGI application
    """
    def __init__(self, app):
        # type: (WSGIApplication) -> None
        self.app = app

    def __call__(self, environ, start_response):
        # type: (WSGIEnvironment, StartResponse) -> Iterable[bytes]
        content_encoding = environ.get('HTTP_CONTENT_ENCODING', '').lower().strip()
        if content_encoding == 'gzip':
            compressed_body = get_input_stream(environ).read()
            body = gzip.GzipFile(fileobj=BytesIO(compressed_body)).read()
            environ['wsgi.input'] = BytesIO(body)
            environ['CONTENT_LENGTH'] = str(len(body))
            del environ['HTTP_CONTENT_ENCODING']
        return self.app(environ, start_response)


def replace_double_slashes(app):
    # type: (WSGIApplication) -> WSGIApplication
    def wrapped_app(environ, start_response):
        # type: (WSGIEnvironment, StartResponse) -> Iterable[bytes]
        environ['PATH_INFO'] = environ['PATH_INFO'].replace('//', '/')
        return app(environ, start_response)
    return wrapped_app


def add_cors_headers(app):
    # type: (WSGIApplication) -> WSGIApplication
    def wrapped_app(environ, start_response):
        # type: (WSGIEnvironment, StartResponse) -> Iterable[bytes]
        def start_response_with_cors_headers(status, headers, exc_info=None):
            # type: (str,  List[Tuple[str, str]], Optional[Any]) -> Callable[[bytes], None]
            headers.append(('Access-Control-Allow-Origin', '*'))
            return start_response(status, headers, exc_info)
        return app(environ, start_response_with_cors_headers)
    return wrapped_app


def make_application(config_path):
    # type: (str) -> Tuple[Server, WSGIApplication]
    """Construct a WSGI application for the AcoustID server

    :param config_path: path to the server configuration file
    """
    server = Server(config_path)
    server.setup_sentry()
    app = GzipRequestMiddleware(server)  # type: WSGIApplication
    app = SentryWsgiMiddleware(app)
    app = replace_double_slashes(app)
    app = add_cors_headers(app)
    app = ProxyFix(app)  # type: ignore
    return server, app
