# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import os
import logging
from werkzeug.exceptions import NotFound
from acoustid.handler import Handler, Response

logger = logging.getLogger(__name__)


class PageHandler(Handler):

    def __init__(self, config, templates, filename):
        self.config = config
        self.templates = templates
        self.filename = filename

    @classmethod
    def create_from_server(cls, server, page=None):
        filename = os.path.normpath(
            os.path.join(server.config.website.pages_path,
                         page + '.md'))
        return cls(server.config.website, server.templates, filename)

    def render_template(self, name, **params):
        context = {
            'base_url': self.config.base_url,
            'base_https_url': self.config.base_https_url or self.config.base_url,
        }
        context.update(params)
        html = self.templates.get_template(name).render(**context)
        return Response(html, content_type='text/html; charset=UTF-8')


    def handle(self, req):
        from markdown import markdown
        if not self.filename.startswith(self.config.pages_path):
            logger.warn('Attempting to access page outside of the pages directory: %s', self.filename)
            raise NotFound()
        try:
            text = open(self.filename, 'r').read().decode('utf8')
        except IOError:
            logger.warn('Page does not exist: %s', self.filename)
            raise NotFound()
        return self.render_template('page.html', content=markdown(text))


class IndexHandler(PageHandler):

    @classmethod
    def create_from_server(cls, server):
        return PageHandler.create_from_server(server, page='index')

