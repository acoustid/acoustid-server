# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import gzip
import sentry_sdk
from sentry_sdk.integrations.wsgi import SentryWsgiMiddleware
from cStringIO import StringIO
from werkzeug.exceptions import HTTPException
from werkzeug.routing import Map, Rule, Submount
from werkzeug.wrappers import Request
from werkzeug.contrib.fixers import ProxyFix
from acoustid import api
from acoustid.script import Script
import api.v1
import api.v2
import api.v2.misc
import api.v2.internal


api_url_rules = [
    Rule('/_health', endpoint=api.HealthHandler),
    Rule('/_health_ro', endpoint=api.ReadOnlyHealthHandler),
    Rule('/_health_docker', endpoint=api.ReadOnlyHealthHandler),
    Rule('/lookup', endpoint=api.v1.LookupHandler),
    Rule('/submit', endpoint=api.v1.SubmitHandler),
    Submount('/v2', [
        Rule('/lookup', endpoint=api.v2.LookupHandler),
        Rule('/submit', endpoint=api.v2.SubmitHandler),
        Rule('/submission_status', endpoint=api.v2.SubmissionStatusHandler),
        Rule('/fingerprint', endpoint=api.v2.misc.GetFingerprintHandler),
        Rule('/track/list_by_mbid', endpoint=api.v2.misc.TrackListByMBIDHandler),
        Rule('/track/list_by_puid', endpoint=api.v2.misc.TrackListByPUIDHandler),
        Rule('/user/lookup', endpoint=api.v2.misc.UserLookupHandler),
        Rule('/user/create_anonymous', endpoint=api.v2.misc.UserCreateAnonymousHandler),
        Rule('/user/create_musicbrainz', endpoint=api.v2.misc.UserCreateMusicBrainzHandler),
        Submount('/internal', [
            Rule('/update_lookup_stats', endpoint=api.v2.internal.UpdateLookupStatsHandler),
            Rule('/update_user_agent_stats', endpoint=api.v2.internal.UpdateUserAgentStatsHandler),
            Rule('/lookup_stats', endpoint=api.v2.internal.LookupStatsHandler),
            Rule('/create_account', endpoint=api.v2.internal.CreateAccountHandler),
            Rule('/create_application', endpoint=api.v2.internal.CreateApplicationHandler),
            Rule('/update_application_status', endpoint=api.v2.internal.UpdateApplicationStatusHandler),
        ]),
    ]),
]

admin_url_rules = [
    Submount('/admin', [
    ])
]


class Server(Script):

    def __init__(self, config_path):
        super(Server, self).__init__(config_path)
        url_rules = api_url_rules + admin_url_rules
        self.url_map = Map(url_rules, strict_slashes=False)

    def __call__(self, environ, start_response):
        urls = self.url_map.bind_to_environ(environ)
        handler = None
        try:
            try:
                handler_class, args = urls.match()
                handler = handler_class.create_from_server(self, **args)
                response = handler.handle(Request(environ))
            except HTTPException, e:
                return e(environ, start_response)
            return response(environ, start_response)
        finally:
            if handler is not None and 'conn' in handler.__dict__:
                handler.__dict__['conn'].close()

    def setup_sentry(self):
        sentry_sdk.init(self.config.sentry.api_dsn)


class GzipRequestMiddleware(object):
    """WSGI middleware to handle GZip-compressed HTTP requests bodies

    :param app: a WSGI application
    """
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # XXX can we do this without loading everything into memory?
        content_encoding = environ.get('HTTP_CONTENT_ENCODING', '').lower().strip()
        if content_encoding == 'gzip' and 'wsgi.input' in environ and 'CONTENT_LENGTH' in environ:
            compressed_body = environ['wsgi.input'].read(int(environ['CONTENT_LENGTH']))
            body = gzip.GzipFile(fileobj=StringIO(compressed_body)).read()
            environ['wsgi.input'] = StringIO(body)
            environ['CONTENT_LENGTH'] = str(len(body))
            del environ['HTTP_CONTENT_ENCODING']
        return self.app(environ, start_response)


def make_application(config_path):
    """Construct a WSGI application for the AcoustID server

    :param config_path: path to the server configuration file
    """
    server = Server(config_path)
    server.setup_sentry()
    app = GzipRequestMiddleware(server)
    app = ProxyFix(app)
    app = SentryWsgiMiddleware(app)
    return server, app
