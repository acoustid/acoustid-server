# Copyright (C) 2014 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from sqlalchemy.orm import sessionmaker


class Database(object):

    def __init__(self):
        self.session_factory = sessionmaker()
        self.session = None


db = Database()
