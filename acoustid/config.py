# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import os.path
import logging
import ConfigParser
from sqlalchemy import create_engine
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

    def create_engine(self, superuser=False, **kwargs):
        return create_engine(self.create_url(superuser=superuser), **kwargs)

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


class RedisConfig(object):

    def __init__(self):
        self.host = '127.0.0.1'
        self.port = 6379

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
        self.debug = False
        self.secret = None
        self.mb_oauth_client_id = None
        self.mb_oauth_client_secret = None
        self.google_oauth_client_id = None
        self.google_oauth_client_secret = None
        self.maintenance = False

    def read(self, parser, section):
        if parser.has_option(section, 'debug'):
            self.debug = parser.getboolean(section, 'debug')
        self.secret = parser.get(section, 'secret')
        if parser.has_option(section, 'mb_oauth_client_id'):
            self.mb_oauth_client_id = parser.get(section, 'mb_oauth_client_id')
        if parser.has_option(section, 'mb_oauth_client_secret'):
            self.mb_oauth_client_secret = parser.get(section, 'mb_oauth_client_secret')
        if parser.has_option(section, 'google_oauth_client_id'):
            self.google_oauth_client_id = parser.get(section, 'google_oauth_client_id')
        if parser.has_option(section, 'google_oauth_client_secret'):
            self.google_oauth_client_secret = parser.get(section, 'google_oauth_client_secret')
        if parser.has_option(section, 'maintenance'):
            self.maintenance = parser.getboolean(section, 'maintenance')


class ReplicationConfig(object):

    def __init__(self):
        self.import_acoustid = None
        self.import_acoustid_musicbrainz = None

    def read(self, parser, section):
        if parser.has_option(section, 'import_acoustid'):
            self.import_acoustid = parser.get(section, 'import_acoustid')
        if parser.has_option(section, 'import_acoustid_musicbrainz'):
            self.import_acoustid_musicbrainz = parser.get(section, 'import_acoustid_musicbrainz')


class ClusterConfig(object):

    def __init__(self):
        self.role = 'master'
        self.base_master_url = None
        self.secret = None

    def read(self, parser, section):
        if parser.has_option(section, 'role'):
            self.role = parser.get(section, 'role')
        if parser.has_option(section, 'base_master_url'):
            self.base_master_url = parser.get(section, 'base_master_url')
        if parser.has_option(section, 'secret'):
            self.secret = parser.get(section, 'secret')


class RateLimiterConfig(object):

    def __init__(self):
        self.ips = {}
        self.applications = {}

    def read(self, parser, section):
        for name in parser.options(section):
            if name.startswith('ip.'):
                self.ips[name.split('.', 1)[1]] = parser.getfloat(section, name)
            elif name.startswith('application.'):
                self.applications[int(name.split('.', 1)[1])] = parser.getfloat(section, name)


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
        self.redis = RedisConfig()
        self.redis.read(parser, 'redis')
        self.replication = ReplicationConfig()
        self.replication.read(parser, 'replication')
        self.cluster = ClusterConfig()
        self.cluster.read(parser, 'cluster')
        self.rate_limiter = RateLimiterConfig()
        self.rate_limiter.read(parser, 'rate_limiter')

