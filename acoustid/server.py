# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

from werkzeug.exceptions import HTTPException
from werkzeug.routing import Map, Rule, Submount
from werkzeug.wrappers import Request, Response
import sqlalchemy
from acoustid.config import Config
from acoustid import api, website, handlers
from acoustid.script import Script


api_url_rules = [
    Submount('/ws', [
        Rule('/lookup', endpoint=api.LookupHandler),
        Rule('/submit', endpoint=api.SubmitHandler),
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

