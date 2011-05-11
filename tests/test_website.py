# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import *
from tests import prepare_database, with_database
from werkzeug.wrappers import Request
from werkzeug.test import EnvironBuilder
from werkzeug.datastructures import MultiDict
from jinja2 import Environment, FileSystemLoader
from acoustid import tables
from acoustid.website import (
    IndexHandler,
    PageHandler,
)



class TestEngine(object):

    def __init__(self, conn):
        self.conn = conn

    def connect(self):
        return self.conn


class TestServer(object):

    def __init__(self, conn):
        from tests import config
        self.engine = TestEngine(conn)
        self.config = config
        loader = FileSystemLoader(self.config.website.templates_path)
        self.templates = Environment(loader=loader)


@with_database
def test_index_handler(conn):
    server = TestServer(conn)
    builder = EnvironBuilder(method='GET', data={})
    handler = IndexHandler.create_from_server(server)
    resp = handler.handle(Request(builder.get_environ()))
    assert_equals('text/html; charset=UTF-8', resp.content_type)
    assert '<h2>Welcome to Acoustid!</h2>' in resp.data
    assert_equals('200 OK', resp.status)


@with_database
def test_page_handler(conn):
    server = TestServer(conn)
    builder = EnvironBuilder(method='GET', data={})
    handler = PageHandler.create_from_server(server, page='chromaprint')
    resp = handler.handle(Request(builder.get_environ()))
    assert_equals('text/html; charset=UTF-8', resp.content_type)
    assert '<h2>Chromaprint</h2>' in resp.data
    assert_equals('200 OK', resp.status)

