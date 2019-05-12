# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import os.path
import logging
import ConfigParser
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL

logger = logging.getLogger(__name__)


def str_to_bool(x):
    return x.lower() in ('1', 'on', 'true')


def read_env_item(obj, key, name, convert=None):
    value = None
    if name in os.environ:
        value = os.environ[name]
    if name + '_FILE' in os.environ:
        value = open(os.environ[name + '_FILE']).read().strip()
    if value is not None:
        if convert is not None:
            value = convert(value)
        setattr(obj, key, value)


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

    def read_env(self, prefix):
        read_env_item(self, 'name', prefix + 'POSTGRES_DB')
        read_env_item(self, 'host', prefix + 'POSTGRES_HOST')
        read_env_item(self, 'port', prefix + 'POSTGRES_PORT', convert=int)
        read_env_item(self, 'user', prefix + 'POSTGRES_USER')
        read_env_item(self, 'password', prefix + 'POSTGRES_PASSWORD')


class IndexConfig(object):

    def __init__(self):
        self.host = '127.0.0.1'
        self.port = 6080

    def read(self, parser, section):
        if parser.has_option(section, 'host'):
            self.host = parser.get(section, 'host')
        if parser.has_option(section, 'port'):
            self.port = parser.getint(section, 'port')

    def read_env(self, prefix):
        read_env_item(self, 'host', prefix + 'INDEX_HOST')
        read_env_item(self, 'port', prefix + 'INDEX_PORT', convert=int)


class RedisConfig(object):

    def __init__(self):
        self.host = '127.0.0.1'
        self.port = 6379

    def read(self, parser, section):
        if parser.has_option(section, 'host'):
            self.host = parser.get(section, 'host')
        if parser.has_option(section, 'port'):
            self.port = parser.getint(section, 'port')

    def read_env(self, prefix):
        read_env_item(self, 'host', prefix + 'REDIS_HOST')
        read_env_item(self, 'port', prefix + 'REDIS_PORT', convert=int)


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

    def read_env(self, prefix):
        pass  # XXX


class WebSiteConfig(object):

    def __init__(self):
        self.debug = False
        self.secret = None
        self.mb_oauth_client_id = None
        self.mb_oauth_client_secret = None
        self.google_oauth_client_id = None
        self.google_oauth_client_secret = None
        self.maintenance = False
        self.shutdown_delay = 0

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
        if parser.has_option(section, 'shutdown_delay'):
            self.shutdown_delay = parser.getint(section, 'shutdown_delay')

    def read_env(self, prefix):
        read_env_item(self, 'debug', prefix + 'DEBUG', convert=str_to_bool)
        read_env_item(self, 'maintenance', prefix + 'MAINTENANCE', convert=str_to_bool)
        read_env_item(self, 'mb_oauth_client_id', prefix + 'MB_OAUTH_CLIENT_ID')
        read_env_item(self, 'mb_oauth_client_secret', prefix + 'MB_OAUTH_CLIENT_SECRET')
        read_env_item(self, 'google_oauth_client_id', prefix + 'GOOGLE_OAUTH_CLIENT_ID')
        read_env_item(self, 'google_oauth_client_secret', prefix + 'GOOGLE_OAUTH_CLIENT_SECRET')
        read_env_item(self, 'shutdown_delay', prefix + 'SHUTDOWN_DELAY', convert=int)


class SentryConfig(object):

    def __init__(self):
        self.web_dsn = ''
        self.api_dsn = ''
        self.script_dsn = ''

    def read(self, parser, section):
        if parser.has_section(section):
            return
        if parser.has_option(section, 'web_dsn'):
            self.web_dsn = parser.get(section, 'web_dsn')
        if parser.has_option(section, 'api_dsn'):
            self.api_dsn = parser.get(section, 'web_dsn')
        if parser.has_option(section, 'script_dsn'):
            self.script_dsn = parser.get(section, 'web_dsn')

    def read_env(self, prefix):
        read_env_item(self, 'web_dsn', prefix + 'SENTRY_WEB_DSN')
        read_env_item(self, 'api_dsn', prefix + 'SENTRY_WEB_DSN')
        read_env_item(self, 'script_dsn', prefix + 'SENTRY_SCRIPT_DSN')


class ReplicationConfig(object):

    def __init__(self):
        self.import_acoustid = None
        self.import_acoustid_musicbrainz = None

    def read(self, parser, section):
        if parser.has_option(section, 'import_acoustid'):
            self.import_acoustid = parser.get(section, 'import_acoustid')
        if parser.has_option(section, 'import_acoustid_musicbrainz'):
            self.import_acoustid_musicbrainz = parser.get(section, 'import_acoustid_musicbrainz')

    def read_env(self, prefix):
        pass  # XXX


class ClusterConfig(object):

    def __init__(self):
        self.role = 'master'
        self.base_master_url = None
        self.secret = None

    def read(self, parser, section):
        if parser.has_section(section):
            return
        if parser.has_option(section, 'role'):
            self.role = parser.get(section, 'role')
        if parser.has_option(section, 'base_master_url'):
            self.base_master_url = parser.get(section, 'base_master_url')
        if parser.has_option(section, 'secret'):
            self.secret = parser.get(section, 'secret')

    def read_env(self, prefix):
        read_env_item(self, 'role', prefix + 'CLUSTER_ROLE')
        read_env_item(self, 'base_master_url', prefix + 'CLUSTER_BASE_MASTER_URL')
        read_env_item(self, 'secret', prefix + 'CLUSTER_SECRET')


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

    def read_env(self, prefix):
        pass  # XXX


class Config(object):

    def __init__(self):
        self.database = DatabaseConfig()
        self.logging = LoggingConfig()
        self.website = WebSiteConfig()
        self.index = IndexConfig()
        self.redis = RedisConfig()
        self.replication = ReplicationConfig()
        self.cluster = ClusterConfig()
        self.rate_limiter = RateLimiterConfig()
        self.sentry = SentryConfig()

    def read(self, path):
        logger.info("Loading configuration file %s", path)
        parser = ConfigParser.RawConfigParser()
        parser.read(path)
        self.database.read(parser, 'database')
        self.logging.read(parser, 'logging')
        self.website.read(parser, 'website')
        self.index.read(parser, 'index')
        self.redis.read(parser, 'redis')
        self.replication.read(parser, 'replication')
        self.cluster.read(parser, 'cluster')
        self.rate_limiter.read(parser, 'rate_limiter')
        self.sentry.read(parser, 'sentry')

    def read_env(self, tests=False):
        if tests:
            prefix = 'ACOUSTID_TEST_'
        else:
            prefix = 'ACOUSTID_'
        self.database.read_env(prefix)
        self.logging.read_env(prefix)
        self.website.read_env(prefix)
        self.index.read_env(prefix)
        self.redis.read_env(prefix)
        self.replication.read_env(prefix)
        self.cluster.read_env(prefix)
        self.rate_limiter.read_env(prefix)
        self.sentry.read_env(prefix)
