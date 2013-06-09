# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import sys
import logging
import sqlalchemy
import sqlalchemy.pool
from redis import Redis
from optparse import OptionParser
from acoustid.config import Config
from acoustid.indexclient import IndexClientPool
from acoustid.utils import LocalSysLogHandler

logger = logging.getLogger(__name__)


class Script(object):

    def __init__(self, config_path):
        self.config = Config(config_path)
        #self.engine = sqlalchemy.create_engine(self.config.database.create_url(),
        #    poolclass=sqlalchemy.pool.AssertionPool)
        self.engine = sqlalchemy.create_engine(self.config.database.create_url())
        if not self.config.index.host:
            self.index = None
        else:
            self.index = IndexClientPool(host=self.config.index.host,
                                         port=self.config.index.port,
                                         recycle=60)
        if not self.config.redis.host:
            self.redis = None
        else:
            self.redis = Redis(host=self.config.redis.host,
                               port=self.config.redis.port)
        self.setup_logging()

    def setup_logging(self):
        for logger_name, level in sorted(self.config.logging.levels.items()):
            logging.getLogger(logger_name).setLevel(level)
        if self.config.logging.syslog:
            handler = LocalSysLogHandler(ident='acoustid',
                facility=self.config.logging.syslog_facility, log_pid=True)
            handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))
            logging.getLogger().addHandler(handler)

    def setup_console_logging(self, quiet=False):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s - %(message)s', '%H:%M:%S'))
        if quiet:
            handler.setLevel(logging.ERROR)
        logging.getLogger().addHandler(handler)



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
    if master_only and script.config.cluster.role != 'master':
        logger.debug("Not running script %s on a slave server", sys.argv[0])
    else:
        logger.debug("Running script %s", sys.argv[0])
        try:
            func(script, options, args)
        except:
            logger.exception("Script finished %s with an exception", sys.argv[0])
            raise
        else:
            logger.debug("Script finished %s successfuly", sys.argv[0])
    script.engine.dispose()
    script.index.dispose()

