# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

import sys
import logging
import logging.handlers
import sqlalchemy
from optparse import OptionParser
from acoustid.config import Config

logger = logging.getLogger(__name__)


class Script(object):

    def __init__(self, config_path):
        self.config = Config(config_path)
        self.engine = sqlalchemy.create_engine(self.config.database.create_url())
        self.setup_logging()

    def setup_logging(self):
        for logger_name, level in sorted(self.config.logging.levels.items()):
            logging.getLogger(logger_name).setLevel(level)
        if self.config.logging.syslog:
            handler = logging.handlers.SysLogHandler(address='/dev/log', facility=self.config.logging.syslog_facility)
            handler.setFormatter(logging.Formatter('acoustid[%(process)s]: %(name)s: %(message)s'))
            logging.getLogger().addHandler(handler)

    def setup_console_logging(self, quiet=False):
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s - %(message)s', '%H:%M:%S'))
        if quiet:
            handler.setLevel(logging.ERROR)
        logging.getLogger().addHandler(handler)



def run_script(func):
    parser = OptionParser()
    parser.add_option("-c", "--config", dest="config",
        help="configuration file", metavar="FILE")
    parser.add_option("-q", "--quiet", dest="quiet", action="store_true",
        default=False, help="don't print info messages to stdout")
    (options, args) = parser.parse_args()
    if not options.config:
        parser.error('no configuration file')
    script = Script(options.config)
    script.setup_console_logging(options.quiet)
    logger.info("Running script %s", sys.argv[0])
    try:
        func(script, options, args)
    except:
        logger.exception("Script finished %s with an exception", sys.argv[0])
        raise
    else:
        logger.info("Script finished %s successfuly", sys.argv[0])

