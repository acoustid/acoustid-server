# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

import gzip
from cStringIO import StringIO
from werkzeug.exceptions import HTTPException
from werkzeug.routing import Map, Rule, Submount
from werkzeug.wrappers import Request, Response
import sqlalchemy
from acoustid.config import Config
from acoustid import api, website, handlers
from acoustid.script import Script
import api.v2


api_url_rules = [
    Submount('/ws', [
        Submount('/v2', [
            Rule('/lookup', endpoint=api.v2.LookupHandler),
            Rule('/submit', endpoint=api.v2.SubmitHandler),
        ])
    ])
]

admin_url_rules = [
    Submount('/admin', [
    ])
]

website_url_rules = [
    Rule('/', endpoint=website.IndexHandler),
]


class Server(Script):

    def __init__(self, config_path):
        super(Server, self).__init__(config_path)
        url_rules = website_url_rules + api_url_rules + admin_url_rules
        self.url_map = Map(url_rules, strict_slashes=False)

    def __call__(self, environ, start_response):
        urls = self.url_map.bind_to_environ(environ)
        try:
            handler_class, args = urls.match()
            handler = handler_class.create_from_server(self)
            response = handler.handle(Request(environ))
        except HTTPException, e:
            return e(environ, start_response)
        return response(environ, start_response)


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

