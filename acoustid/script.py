# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

import logging
import sqlalchemy
from acoustid.config import Config

logger = logging.getLogger(__name__)


class Script(object):

    def __init__(self, config_path):
        self.config = Config(config_path)
        self.engine = sqlalchemy.create_engine(self.config.database.create_url())

