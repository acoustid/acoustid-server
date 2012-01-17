# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import gzip
from cStringIO import StringIO
from werkzeug.exceptions import HTTPException
from werkzeug.routing import Map, Rule, Submount
from werkzeug.wrappers import Request, Response
from jinja2 import Environment, FileSystemLoader
import sqlalchemy
from acoustid.config import Config
from acoustid import api, website, handlers
from acoustid.script import Script
import api.v1
import api.v2
import api.v2.misc


api_url_rules = [
    Submount('/ws', [
        Rule('/lookup', endpoint=api.v1.LookupHandler),
        Rule('/submit', endpoint=api.v1.SubmitHandler),
        Submount('/v2', [
            Rule('/lookup', endpoint=api.v2.LookupHandler),
            Rule('/submit', endpoint=api.v2.SubmitHandler),
            Rule('/track/list_by_mbid', endpoint=api.v2.misc.TrackListByMBIDHandler),
            Rule('/track/list_by_puid', endpoint=api.v2.misc.TrackListByPUIDHandler),
            Rule('/user/lookup', endpoint=api.v2.misc.UserLookupHandler),
            Rule('/user/create_anonymous', endpoint=api.v2.misc.UserCreateAnonymousHandler),
        ]),
    ])
]

admin_url_rules = [
    Submount('/admin', [
    ])
]

website_url_rules = [
    Rule('/', endpoint=website.IndexHandler),
    Rule('/login', endpoint=website.LoginHandler),
    Rule('/logout', endpoint=website.LogoutHandler),
    Rule('/api-key', endpoint=website.APIKeyHandler),
    Rule('/new-api-key', endpoint=website.NewAPIKeyHandler),
    Rule('/applications', endpoint=website.ApplicationsHandler),
    Rule('/application/<int:id>', endpoint=website.ApplicationHandler),
    Rule('/edit/application/<int:id>', endpoint=website.EditApplicationHandler),
    Rule('/new-application', endpoint=website.NewApplicationHandler),
    Rule('/stats', endpoint=website.StatsHandler),
    Rule('/contributors', endpoint=website.ContributorsHandler),
    Rule('/track/<string:id>', endpoint=website.TrackHandler),
    Rule('/fingerprint/<int:id>', endpoint=website.FingerprintHandler),
    Rule('/mbid/<string:mbid>', endpoint=website.MBIDHandler),
    Rule('/puid/<string:puid>', endpoint=website.PUIDHandler),
    Rule('/edit/toggle-track-mbid', endpoint=website.EditToggleTrackMBIDHandler),
    Rule('/<path:page>', endpoint=website.PageHandler),
]


class Server(Script):

    def __init__(self, config_path):
        super(Server, self).__init__(config_path)
        url_rules = website_url_rules + api_url_rules + admin_url_rules
        self.url_map = Map(url_rules, strict_slashes=False)
        self._setup_website()

    def _setup_website(self):
        loader = FileSystemLoader(self.config.website.templates_path)
        self.templates = Environment(loader=loader)

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
    """Construct a WSGI application for the Acoustid server

    :param config_path: path to the server configuration file
    """
    app = Server(config_path)
    app = GzipRequestMiddleware(app)
    return app

