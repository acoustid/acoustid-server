# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import os.path
import logging
from typing import Any, Callable, Dict, List, Optional
from six.moves.configparser import RawConfigParser
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL

from acoustid.const import DEFAULT_GLOBAL_RATE_LIMIT

logger = logging.getLogger(__name__)


def str_to_bool(x):
    # type: (str) -> bool
    return x.lower() in ('1', 'on', 'true')


def read_config_secret_str_option(parser, section, obj, key, name):
    value = None
    if parser.has_option(section, name):
        value = parser.get(section, name)
    elif parser.has_option(section, name + '_file'):
        value_file_path = parser.get(section, name + '_file')
        value = open(value_file_path, 'rt').read().strip()
    if value is not None:
        setattr(obj, key, value)


def read_config_str_option(parser, section, obj, key, name):
    value = None
    if parser.has_option(section, name):
        value = parser.get(section, name)
    if value is not None:
        setattr(obj, key, value)


def read_env_item(obj, key, name, convert=None):
    # type: (Any, str, str, Callable[[str], Any]) -> None
    value = None
    if name in os.environ:
        value = os.environ[name]
        logger.info('Reading config value from environment variable %s', name)
    if name + '_FILE' in os.environ:
        value = open(os.environ[name + '_FILE']).read().strip()
        logger.info('Reading config value from environment variable %s', name + '_FILE')
    if value is not None:
        if convert is not None:
            value = convert(value)
        setattr(obj, key, value)


class BaseConfig(object):

    def read(self, parser, section):
        # type: (RawConfigParser, str) -> None
        if parser.has_section(section):
            self.read_section(parser, section)

    def read_section(self, parser, section):
        # type: (RawConfigParser, str) -> None
        pass

    def read_env(self, prefix):
        # type: (str) -> None
        pass


class DatabasesConfig(BaseConfig):

    def __init__(self):
        # type: () -> None
        self.database_names = ['app', 'fingerprint', 'ingest', 'musicbrainz']
        self.databases = {}  # type: Dict[str, DatabaseConfig]
        for name in self.database_names:
            self.databases[name] = DatabaseConfig()
            self.databases[name + ':ro'] = DatabaseConfig()
        self.use_two_phase_commit = False
        self.use_auto_commit = False

    def create_engines(self, **kwargs):
        # type: (**Any) -> Dict[str, Engine]
        engines = {}  # type: Dict[str, Engine]
        for name, db_config in self.databases.items():
            for other_name, other_db_config in self.databases.items():
                if other_name in engines and other_db_config == db_config:
                    engines[name] = engines[other_name]
                    break
            else:
                engines[name] = db_config.create_engine(**kwargs)
        return engines

    def read_section(self, parser, section):
        # type: (RawConfigParser, str) -> None
        if parser.has_option(section, 'two_phase_commit'):
            self.use_two_phase_commit = parser.getboolean(section, 'two_phase_commit')
        if parser.has_option(section, 'auto_commit'):
            self.use_auto_commit = parser.getboolean(section, 'auto_commit')
        for name, sub_config in self.databases.items():
            sub_section = '{}:{}'.format(section, name)
            if parser.has_section(sub_section):
                sub_config.read(parser, sub_section)
            elif sub_section.endswith(':ro') and parser.has_section(sub_section.replace(':ro', '')):
                sub_config.read(parser, sub_section.replace(':ro', ''))

    def read_env(self, prefix):
        # type: (str) -> None
        read_env_item(self, 'use_auto_commit', prefix + 'DATABASE_AUTO_COMMIT', convert=str_to_bool)
        read_env_item(self, 'use_two_phase_commit', prefix + 'DATABASE_TWO_PHASE_COMMIT', convert=str_to_bool)
        for name, sub_config in self.databases.items():
            sub_prefix = prefix + 'DATABASE_' + name.replace(':', '_').upper() + '_'
            sub_config.read_env(sub_prefix)


class DatabaseConfig(BaseConfig):

    def __init__(self):
        # type: () -> None
        self.user = 'acoustid'
        self.name = 'acoustid'
        self.host = 'localhost'
        self.port = 5432
        self.password = ''
        self.pool_size = 20  # type: Optional[int]
        self.pool_recycle = None  # type: Optional[int]
        self.pool_pre_ping = None  # type: Optional[bool]
        self.pool_timeout = 2  # type: Optional[int]

    def __eq__(self, other):
        # type: (object) -> bool
        if not isinstance(other, DatabaseConfig):
            return False
        return (
            self.user == other.user and
            self.name == other.name and
            self.host == other.host and
            self.port == other.port and
            self.password == other.password and
            self.pool_size == other.pool_size and
            self.pool_recycle == other.pool_recycle and
            self.pool_pre_ping == other.pool_pre_ping and
            self.pool_timeout == other.pool_timeout
        )

    def create_url(self):
        # type: () -> URL
        kwargs = {}  # type: Dict[str, Any]
        kwargs['username'] = self.user
        kwargs['database'] = self.name
        if self.host is not None:
            kwargs['host'] = self.host
        if self.port is not None:
            kwargs['port'] = self.port
        if self.password is not None:
            kwargs['password'] = self.password
        return URL('postgresql', **kwargs)

    def create_engine(self, **kwargs):
        # type: (**Any) -> Engine
        if 'poolclass' not in kwargs:
            if self.pool_size is not None and 'pool_size' not in kwargs:
                kwargs['pool_size'] = self.pool_size
            if self.pool_recycle is not None and 'pool_recycle' not in kwargs:
                kwargs['pool_recycle'] = self.pool_recycle
            if self.pool_pre_ping is not None and 'pool_pre_ping' not in kwargs:
                kwargs['pool_pre_ping'] = self.pool_pre_ping
            if self.pool_timeout is not None and 'pool_timeout' not in kwargs:
                kwargs['pool_timeout'] = self.pool_timeout
        return create_engine(self.create_url(), **kwargs)

    def create_psql_args(self):
        # type: () -> List[str]
        args = []
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

    def read_section(self, parser, section):
        # type: (RawConfigParser, str) -> None
        self.name = parser.get(section, 'name')
        if parser.has_option(section, 'host'):
            self.host = parser.get(section, 'host')
        if parser.has_option(section, 'port'):
            self.port = parser.getint(section, 'port')
        read_config_secret_str_option(parser, section, self, 'user', 'user')
        read_config_secret_str_option(parser, section, self, 'password', 'password')
        if parser.has_option(section, 'pool_size'):
            self.pool_size = parser.getint(section, 'pool_size')
        if parser.has_option(section, 'pool_recycle'):
            self.pool_recycle = parser.getint(section, 'pool_recycle')
        if parser.has_option(section, 'pool_pre_ping'):
            self.pool_pre_ping = parser.getboolean(section, 'pool_pre_ping')
        if parser.has_option(section, 'pool_timeout'):
            self.pool_timeout = parser.getint(section, 'pool_timeout')

    def read_env(self, prefix):
        read_env_item(self, 'name', prefix + 'NAME')
        read_env_item(self, 'host', prefix + 'HOST')
        read_env_item(self, 'port', prefix + 'PORT', convert=int)
        read_env_item(self, 'user', prefix + 'USER')
        read_env_item(self, 'password', prefix + 'PASSWORD')
        read_env_item(self, 'pool_size', prefix + 'POOL_SIZE', convert=int)
        read_env_item(self, 'pool_recycle', prefix + 'POOL_RECYCLE', convert=int)
        read_env_item(self, 'pool_pre_ping', prefix + 'POOL_PRE_PING', convert=str_to_bool)
        read_env_item(self, 'pool_timeout', prefix + 'POOL_TIMEOUT', convert=int)


class IndexConfig(BaseConfig):

    def __init__(self):
        # type: () -> None
        self.host = '127.0.0.1'
        self.port = 6080

    def read_section(self, parser, section):
        # type: (RawConfigParser, str) -> None
        if parser.has_option(section, 'host'):
            self.host = parser.get(section, 'host')
        if parser.has_option(section, 'port'):
            self.port = parser.getint(section, 'port')

    def read_env(self, prefix):
        read_env_item(self, 'host', prefix + 'INDEX_HOST')
        read_env_item(self, 'port', prefix + 'INDEX_PORT', convert=int)


class RedisConfig(BaseConfig):

    def __init__(self):
        self.host = '127.0.0.1'
        self.port = 6379
        self.sentinel = False
        self.cluster = 'acoustid'
        self.password = None

    def read_section(self, parser, section):
        # type: (RawConfigParser, str) -> None
        if parser.has_option(section, 'host'):
            self.host = parser.get(section, 'host')
        if parser.has_option(section, 'port'):
            self.port = parser.getint(section, 'port')
        if parser.has_option(section, 'sentinel'):
            self.sentinel = parser.getboolean(section, 'sentinel')
        if parser.has_option(section, 'cluster'):
            self.cluster = parser.get(section, 'cluster')
        read_config_secret_str_option(parser, section, self, 'password', 'password')

    def read_env(self, prefix):
        read_env_item(self, 'host', prefix + 'REDIS_HOST')
        read_env_item(self, 'port', prefix + 'REDIS_PORT', convert=int)
        read_env_item(self, 'sentinel', prefix + 'SENTINEL', convert=str_to_bool)
        read_env_item(self, 'cluster', prefix + 'REDIS_CLUSTER')
        read_env_item(self, 'password', prefix + 'REDIS_PASSWORD')


def get_logging_level_names():
    try:
        return logging._levelNames
    except AttributeError:
        level_names = {}
        for value, name in logging._levelToName.items():
            level_names[name] = value
        return level_names


class LoggingConfig(BaseConfig):

    def __init__(self):
        self.levels = {}
        self.syslog = False
        self.syslog_facility = None

    def read_section(self, parser, section):
        # type: (RawConfigParser, str) -> None
        level_names = get_logging_level_names()
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


class WebSiteConfig(BaseConfig):

    def __init__(self):
        self.debug = False
        self.secret = None
        self.mb_oauth_client_id = None
        self.mb_oauth_client_secret = None
        self.google_oauth_client_id = None
        self.google_oauth_client_secret = None
        self.maintenance = False
        self.shutdown_delay = 0
        self.shutdown_file_path = '/tmp/acoustid-server-shutdown.txt'
        self.search_timeout = 1.0
        self.search_return_metadata = True

    def read_section(self, parser, section):
        # type: (RawConfigParser, str) -> None
        read_config_secret_str_option(parser, section, self, 'secret', 'secret')
        read_config_secret_str_option(parser, section, self, 'mb_oauth_client_id', 'mb_oauth_client_id')
        read_config_secret_str_option(parser, section, self, 'mb_oauth_client_secret', 'mb_oauth_client_secret')
        read_config_secret_str_option(parser, section, self, 'google_oauth_client_id', 'mb_oauth_client_id')
        read_config_secret_str_option(parser, section, self, 'google_oauth_client_secret', 'mb_oauth_client_secret')
        if parser.has_option(section, 'debug'):
            self.debug = parser.getboolean(section, 'debug')
        if parser.has_option(section, 'maintenance'):
            self.maintenance = parser.getboolean(section, 'maintenance')
        if parser.has_option(section, 'shutdown_delay'):
            self.shutdown_delay = parser.getint(section, 'shutdown_delay')
        if parser.has_option(section, 'search_timeout'):
            self.search_timeout = parser.getfloat(section, 'search_timeout')
        if parser.has_option(section, 'search_return_metadata'):
            self.search_return_metadata = parser.getboolean(section, 'search_return_metadata')

    def read_env(self, prefix):
        read_env_item(self, 'debug', prefix + 'DEBUG', convert=str_to_bool)
        read_env_item(self, 'maintenance', prefix + 'MAINTENANCE', convert=str_to_bool)
        read_env_item(self, 'secret', prefix + 'SECRET')
        read_env_item(self, 'mb_oauth_client_id', prefix + 'MB_OAUTH_CLIENT_ID')
        read_env_item(self, 'mb_oauth_client_secret', prefix + 'MB_OAUTH_CLIENT_SECRET')
        read_env_item(self, 'google_oauth_client_id', prefix + 'GOOGLE_OAUTH_CLIENT_ID')
        read_env_item(self, 'google_oauth_client_secret', prefix + 'GOOGLE_OAUTH_CLIENT_SECRET')
        read_env_item(self, 'shutdown_delay', prefix + 'SHUTDOWN_DELAY', convert=int)


class GunicornConfig(BaseConfig):

    def __init__(self):
        # type: () -> None
        self.timeout = 90
        self.workers = 1
        self.threads = 1
        self.backlog = 1024

    def read_section(self, parser, section):
        # type: (RawConfigParser, str) -> None
        if parser.has_option(section, 'timeout'):
            self.timeout = parser.getint(section, 'timeout')
        if parser.has_option(section, 'workers'):
            self.workers = parser.getint(section, 'workers')
        if parser.has_option(section, 'threads'):
            self.threads = parser.getint(section, 'threads')
        if parser.has_option(section, 'backlog'):
            self.backlog = parser.getint(section, 'backlog')

    def read_env(self, prefix):
        # type: (str) -> None
        read_env_item(self, 'timeout', prefix + 'GUNICORN_TIMEOUT', convert=int)
        read_env_item(self, 'workers', prefix + 'GUNICORN_WORKERS', convert=int)
        read_env_item(self, 'threads', prefix + 'GUNICORN_THREADS', convert=int)
        read_env_item(self, 'backlog', prefix + 'GUNICORN_BACKLOG', convert=int)


class uWSGIConfig(BaseConfig):

    def __init__(self):
        self.harakiri = 120
        self.http_timeout = 90
        self.http_connect_timeout = 10
        self.workers = 2
        self.post_buffering = 0
        self.buffer_size = 10240
        self.offload_threads = 1

    def read_section(self, parser, section):
        # type: (RawConfigParser, str) -> None
        if parser.has_option(section, 'harakiri'):
            self.harakiri = parser.getint(section, 'harakiri')
        if parser.has_option(section, 'http_timeout'):
            self.http_timeout = parser.getint(section, 'http_timeout')
        if parser.has_option(section, 'http_connect_timeout'):
            self.http_connect_timeout = parser.getint(section, 'http_connect_timeout')
        if parser.has_option(section, 'workers'):
            self.workers = parser.getint(section, 'workers')
        if parser.has_option(section, 'post_buffering'):
            self.post_buffering = parser.getint(section, 'post_buffering')
        if parser.has_option(section, 'buffer_size'):
            self.buffer_size = parser.getint(section, 'buffer_size')
        if parser.has_option(section, 'offload_threads'):
            self.offload_threads = parser.getint(section, 'offload_threads')

    def read_env(self, prefix):
        read_env_item(self, 'harakiri', prefix + 'UWSGI_HARAKIRI', convert=int)
        read_env_item(self, 'http_timeout', prefix + 'UWSGI_HTTP_TIMEOUT', convert=int)
        read_env_item(self, 'http_connect_timeout', prefix + 'UWSGI_CONNECT_TIMEOUT', convert=int)
        read_env_item(self, 'workers', prefix + 'UWSGI_WORKERS', convert=int)
        read_env_item(self, 'post_buffering', prefix + 'UWSGI_POST_BUFFERING', convert=int)
        read_env_item(self, 'buffer_size', prefix + 'UWSGI_BUFFER_SIZE', convert=int)
        read_env_item(self, 'offload_threads', prefix + 'UWSGI_OFFLOAD_THREADS', convert=int)


class SentryConfig(BaseConfig):

    def __init__(self):
        self.web_dsn = ''
        self.api_dsn = ''
        self.script_dsn = ''

    def read_section(self, parser, section):
        # type: (RawConfigParser, str) -> None
        if parser.has_option(section, 'web_dsn'):
            self.web_dsn = parser.get(section, 'web_dsn')
        if parser.has_option(section, 'api_dsn'):
            self.api_dsn = parser.get(section, 'api_dsn')
        if parser.has_option(section, 'script_dsn'):
            self.script_dsn = parser.get(section, 'script_dsn')

    def read_env(self, prefix):
        read_env_item(self, 'web_dsn', prefix + 'SENTRY_WEB_DSN')
        read_env_item(self, 'api_dsn', prefix + 'SENTRY_API_DSN')
        read_env_item(self, 'script_dsn', prefix + 'SENTRY_SCRIPT_DSN')


class StatsdConfig(BaseConfig):

    def __init__(self):
        # type: () -> None
        self.host = ''
        self.port = 8125
        self.prefix = ''

    @property
    def enabled(self):
        # type: () -> bool
        return bool(self.host)

    def read_section(self, parser, section):
        # type: (RawConfigParser, str) -> None
        if parser.has_option(section, 'host'):
            self.host = parser.get(section, 'host')
        if parser.has_option(section, 'port'):
            self.port = parser.getint(section, 'port')
        if parser.has_option(section, 'prefix'):
            self.prefix = parser.get(section, 'prefix')

    def read_env(self, prefix):
        # type: (str) -> None
        read_env_item(self, 'host', prefix + 'STATSD_HOST')
        read_env_item(self, 'port', prefix + 'STATSD_PORT', convert=int)
        read_env_item(self, 'prefix', prefix + 'STATSD_PREFIX')


class ReplicationConfig(BaseConfig):

    def __init__(self):
        self.import_acoustid = None
        self.import_acoustid_musicbrainz = None

    def read_section(self, parser, section):
        # type: (RawConfigParser, str) -> None
        if parser.has_option(section, 'import_acoustid'):
            self.import_acoustid = parser.get(section, 'import_acoustid')
        if parser.has_option(section, 'import_acoustid_musicbrainz'):
            self.import_acoustid_musicbrainz = parser.get(section, 'import_acoustid_musicbrainz')

    def read_env(self, prefix):
        pass  # XXX


class ClusterConfig(BaseConfig):

    def __init__(self):
        self.role = 'master'
        self.base_master_url = None
        self.secret = None

    def read_section(self, parser, section):
        # type: (RawConfigParser, str) -> None
        read_config_str_option(parser, section, self, 'role', 'role')
        read_config_str_option(parser, section, self, 'base_master_url', 'base_master_url')
        read_config_secret_str_option(parser, section, self, 'secret', 'secret')

    def read_env(self, prefix):
        read_env_item(self, 'role', prefix + 'CLUSTER_ROLE')
        read_env_item(self, 'base_master_url', prefix + 'CLUSTER_BASE_MASTER_URL')
        read_env_item(self, 'secret', prefix + 'CLUSTER_SECRET')


class RateLimiterConfig(BaseConfig):

    def __init__(self):
        self.global_rate_limit = DEFAULT_GLOBAL_RATE_LIMIT
        self.ips = {}
        self.applications = {}

    def read_section(self, parser, section):
        # type: (RawConfigParser, str) -> None
        for name in parser.options(section):
            if name == 'global':
                self.global_rate_limit = parser.getfloat(section, name)
            if name.startswith('ip.'):
                self.ips[name.split('.', 1)[1]] = parser.getfloat(section, name)
            elif name.startswith('application.'):
                self.applications[int(name.split('.', 1)[1])] = parser.getfloat(section, name)

    def read_env(self, prefix):
        pass  # XXX


class Config(object):

    def __init__(self):
        self.databases = DatabasesConfig()
        self.logging = LoggingConfig()
        self.website = WebSiteConfig()
        self.index = IndexConfig()
        self.redis = RedisConfig()
        self.replication = ReplicationConfig()
        self.cluster = ClusterConfig()
        self.rate_limiter = RateLimiterConfig()
        self.sentry = SentryConfig()
        self.gunicorn = GunicornConfig()
        self.statsd = StatsdConfig()

    def read(self, path):
        # type: (str) -> None
        logger.info("Loading configuration file %s", path)
        parser = RawConfigParser()
        parser.read(path)
        self.databases.read(parser, 'database')
        self.logging.read(parser, 'logging')
        self.website.read(parser, 'website')
        self.index.read(parser, 'index')
        self.redis.read(parser, 'redis')
        self.replication.read(parser, 'replication')
        self.cluster.read(parser, 'cluster')
        self.rate_limiter.read(parser, 'rate_limiter')
        self.sentry.read(parser, 'sentry')
        self.gunicorn.read(parser, 'gunicorn')
        self.statsd.read(parser, 'statsd')

    def read_env(self, tests=False):
        # type: (bool) -> None
        if tests:
            prefix = 'ACOUSTID_TEST_'
        else:
            prefix = 'ACOUSTID_'
        self.databases.read_env(prefix)
        self.logging.read_env(prefix)
        self.website.read_env(prefix)
        self.index.read_env(prefix)
        self.redis.read_env(prefix)
        self.replication.read_env(prefix)
        self.cluster.read_env(prefix)
        self.rate_limiter.read_env(prefix)
        self.sentry.read_env(prefix)
        self.gunicorn.read_env(prefix)
        self.statsd.read_env(prefix)
