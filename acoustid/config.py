# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

import logging
import ConfigParser
from sqlalchemy.engine.url import URL

logger = logging.getLogger(__name__)


class DatabaseConfig(object):

    def __init__(self):
        self.user = None
        self.superuser = 'postgres'
        self.name = None
        self.host = None
        self.port = None
        self.password = None

    def create_url(self, superuser=False):
        kwargs = {}
        if superuser:
            kwargs['username'] = self.superuser
        else:
            kwargs['username'] = self.user
        kwargs['database'] = self.name
        if self.host is not None:
            kwargs['host'] = self.host
        if self.port is not None:
            kwargs['port'] = self.port
        if self.password is not None:
            kwargs['password'] = self.password
        return URL('postgresql+psycopg2', **kwargs)

    def read(self, parser, section):
        self.user = parser.get(section, 'user')
        self.name = parser.get(section, 'name')
        if parser.has_option(section, 'host'):
            self.host = parser.get(section, 'host')
        if parser.has_option(section, 'port'):
            self.port = parser.getint(section, 'port')
        if parser.has_option(section, 'password'):
            self.password = parser.get(section, 'password')


class LoggingConfig(object):

    def __init__(self):
        self.levels = {}

    def read(self, parser, section):
        from logging import _levelNames as level_names
        for name in parser.options(section):
            if name == 'level':
                self.levels[''] = level_names[parser.get(section, name)]
            elif name.startswith('level.'):
                self.levels[name.split('.', 1)[1]] = level_names[parser.get(section, name)]


class Config(object):

    def __init__(self, path):
        logger.info("Loading configuration file %s", path)
        parser = ConfigParser.RawConfigParser()
        parser.read(path)
        self.database = DatabaseConfig()
        self.database.read(parser, 'database')
        self.logging = LoggingConfig()
        self.logging.read(parser, 'logging')

