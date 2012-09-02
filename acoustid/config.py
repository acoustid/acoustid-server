# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import os.path
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
        return URL('postgresql', **kwargs)

    def create_psql_args(self, superuser=False):
        args = []
        if superuser:
            args.append('-U')
            args.append(self.superuser)
        else:
            args.append('-U')
            args.append(self.user)
        if self.host is not None:
            args.append('-h')
            args.append(self.host)
        if self.port is not None:
            args.append('-p')
            args.append(str(self.port))
        args.append(self.name)
        return args

    def read(self, parser, section):
        self.user = parser.get(section, 'user')
        self.name = parser.get(section, 'name')
        if parser.has_option(section, 'host'):
            self.host = parser.get(section, 'host')
        if parser.has_option(section, 'port'):
            self.port = parser.getint(section, 'port')
        if parser.has_option(section, 'password'):
            self.password = parser.get(section, 'password')


class IndexConfig(object):

    def __init__(self):
        self.host = '127.0.0.1'
        self.port = 6080

    def read(self, parser, section):
        if parser.has_option(section, 'host'):
            self.host = parser.get(section, 'host')
        if parser.has_option(section, 'port'):
            self.port = parser.getint(section, 'port')


class LoggingConfig(object):

    def __init__(self):
        self.levels = {}
        self.syslog = False
        self.syslog_facility = None

    def read(self, parser, section):
        from logging import _levelNames as level_names
        for name in parser.options(section):
            if name == 'level':
                self.levels[''] = level_names[parser.get(section, name)]
            elif name.startswith('level.'):
                self.levels[name.split('.', 1)[1]] = level_names[parser.get(section, name)]
        if parser.has_option(section, 'syslog'):
            self.syslog = parser.getboolean(section, 'syslog')
        if parser.has_option(section, 'syslog_facility'):
            self.syslog_facility = parser.get(section, 'syslog_facility')


class WebSiteConfig(object):

    def __init__(self):
        root_path = os.path.dirname(__file__) + '/../'
        self.templates_path = os.path.normpath(root_path + 'templates')
        self.pages_path = os.path.normpath(root_path + 'pages')
        self.base_url = 'http://localhost:8080/'
        self.base_https_url = None
        self.secret = None

    def read(self, parser, section):
        if parser.has_option(section, 'base_url'):
            self.base_url = parser.get(section, 'base_url')
        if parser.has_option(section, 'base_https_url'):
            self.base_https_url = parser.get(section, 'base_https_url')
        if not self.base_https_url:
            self.base_https_url = self.base_url
        self.secret = parser.get(section, 'secret')


class ReplicationConfig(object):
    def __init__(self):
        self.import_acoustid = None
        self.import_acoustid_musicbrainz = None

    def read(self, parser, section):
        if parser.has_option(section, 'import_acoustid'):
            self.import_acoustid = parser.get(section, 'import_acoustid')
        if parser.has_option(section, 'import_acoustid_musicbrainz'):
            self.import_acoustid_musicbrainz = parser.get(section, 'import_acoustid_musicbrainz')


class Config(object):

    def __init__(self, path):
        logger.info("Loading configuration file %s", path)
        parser = ConfigParser.RawConfigParser()
        parser.read(path)
        self.database = DatabaseConfig()
        self.database.read(parser, 'database')
        self.logging = LoggingConfig()
        self.logging.read(parser, 'logging')
        self.website = WebSiteConfig()
        self.website.read(parser, 'website')
        self.index = IndexConfig()
        self.index.read(parser, 'index')
        self.replication = ReplicationConfig()
        self.replication.read(parser, 'replication')

