# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import sys
import logging
import sentry_sdk
from statsd import StatsClient
from typing import Any, Optional
from redis import Redis
from redis.sentinel import Sentinel as RedisSentinel
from optparse import OptionParser
from acoustid.config import Config
from acoustid.indexclient import IndexClientPool
from acoustid.utils import LocalSysLogHandler
from acoustid.db import DatabaseContext
from acoustid._release import GIT_RELEASE

logger = logging.getLogger(__name__)


class ScriptContext(object):

    def __init__(self, config, db, redis, index, statsd):
        # type: (Config, DatabaseContext, Redis, IndexClientPool, Optional[StatsClient]) -> None
        self.config = config
        self.db = db
        self.redis = redis
        self.index = index
        self.statsd = statsd

    def __enter__(self):
        # type: () -> ScriptContext
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # type: (Any, Any, Any) -> None
        self.db.close()


class Script(object):

    def __init__(self, config_path, tests=False):
        # type: (str, bool) -> None
        self.config = Config()
        if config_path:
            self.config.read(config_path)
        self.config.read_env(tests=tests)

        self.db_engines = self.config.databases.create_engines()

        if self.config.statsd.enabled:
            self.statsd = StatsClient(host=self.config.statsd.host,
                                      port=self.config.statsd.port,
                                      prefix=self.config.statsd.prefix)
        else:
            self.statsd = None

        self.index = IndexClientPool(host=self.config.index.host,
                                     port=self.config.index.port,
                                     recycle=60)

        self.redis = None
        self.redis_sentinel = None

        if self.config.redis.sentinel:
            self.redis_sentinel = RedisSentinel(
                [(self.config.redis.host, self.config.redis.port)],
                password=self.config.redis.password,
            )
        else:
            self.redis = Redis(
                host=self.config.redis.host,
                port=self.config.redis.port,
                password=self.config.redis.password,
            )

        self._console_logging_configured = False
        if not tests:
            self.setup_logging()

    def get_redis(self):
        # type: () -> Redis
        if self.config.redis.sentinel:
            assert self.redis_sentinel is not None
            return self.redis_sentinel.master_for(self.config.redis.cluster)
        else:
            assert self.redis is not None
            return self.redis

    def setup_logging(self):
        # type: () -> None
        for logger_name, level in sorted(self.config.logging.levels.items()):
            logging.getLogger(logger_name).setLevel(level)
        if self.config.logging.syslog:
            handler = LocalSysLogHandler(ident='acoustid',
                facility=self.config.logging.syslog_facility, log_pid=True)
            handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))
            logging.getLogger().addHandler(handler)
        else:
            self.setup_console_logging()

    def setup_console_logging(self, quiet=False, verbose=False):
        # type: (bool) -> None
        if self._console_logging_configured:
            return
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('[%(asctime)s] [%(process)s] [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S %z'))
        if verbose:
            handler.setLevel(logging.DEBUG)
        if quiet:
            handler.setLevel(logging.ERROR)
        logging.getLogger().addHandler(handler)
        self._console_logging_configured = True

    def setup_sentry(self):
        # type: () -> None
        sentry_sdk.init(self.config.sentry.script_dsn, release=GIT_RELEASE, sample_rate=0.01)

    def context(self, use_two_phase_commit=None):
        # type: (Optional[bool]) -> ScriptContext
        db = DatabaseContext(self, use_two_phase_commit=use_two_phase_commit)
        redis = self.get_redis()
        return ScriptContext(config=self.config, db=db, redis=redis, index=self.index, statsd=self.statsd)


def run_script(func, option_cb=None, master_only=False):
    parser = OptionParser()
    parser.add_option("-c", "--config", dest="config",
        help="configuration file", metavar="FILE")
    parser.add_option("-q", "--quiet", dest="quiet", action="store_true",
        default=False, help="don't print info messages to stdout")
    if option_cb is not None:
        option_cb(parser)
    (options, args) = parser.parse_args()
    if not options.config:
        parser.error('no configuration file')
    script = Script(options.config)
    script.setup_console_logging(options.quiet)
    script.setup_sentry()
    if master_only and script.config.cluster.role != 'master':
        logger.debug("Not running script %s on a slave server", sys.argv[0])
    else:
        logger.debug("Running script %s", sys.argv[0])
        try:
            func(script, options, args)
        except Exception:
            logger.exception("Script finished %s with an exception", sys.argv[0])
            raise
        else:
            logger.debug("Script finished %s successfuly", sys.argv[0])

    for engine in script.db_engines.values():
        engine.dispose()

    script.index.dispose()
