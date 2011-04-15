# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

import os
import sqlalchemy
import sqlalchemy.pool
from contextlib import closing
from nose.tools import make_decorator
from acoustid.config import Config

config = None
engine = None

SEQUENCES = [
    ('account', 'id'),
    ('application', 'id'),
    ('format', 'id'),
    ('track', 'id'),
]

TABLES = [
    'account',
    'application',
]

BASE_SQL = '''
INSERT INTO account (name, apikey) VALUES ('User 1', 'user1key');
INSERT INTO account (name, apikey) VALUES ('User 2', 'user2key');
INSERT INTO application (name, apikey, version, account_id) VALUES ('App 1', 'app1key', '0.1', 1);
INSERT INTO application (name, apikey, version, account_id) VALUES ('App 2', 'app2key', '0.1', 2);
'''

def prepare_database(conn, sql):
    with conn.begin():
        for table, column in SEQUENCES:
            conn.execute("""
                SELECT setval('%(table)s_%(column)s_seq',
                    coalesce((SELECT max(%(column)s) FROM %(table)s), 0) + 1, false)
            """ % {'table': table, 'column': column})
        conn.execute(sql)
        for table, column in SEQUENCES:
            conn.execute("""
                SELECT setval('%(table)s_%(column)s_seq',
                    coalesce((SELECT max(%(column)s) FROM %(table)s), 0) + 1, false)
            """ % {'table': table, 'column': column})


def with_database(func):
    def wrapper(*args, **kwargs):
        with closing(engine.connect()) as conn:
            trans = conn.begin()
            try:
                func(conn, *args, **kwargs)
            finally:
                trans.rollback()
    wrapper = make_decorator(func)(wrapper)
    return wrapper

def setup():
    global config, engine
    config_path = os.path.dirname(os.path.abspath(__file__)) + '/../acoustid-test.conf'
    config = Config(config_path)
    engine = sqlalchemy.create_engine(config.database.create_url(),
        poolclass=sqlalchemy.pool.AssertionPool)
    with closing(engine.connect()) as conn:
        for table in TABLES:
            conn.execute("TRUNCATE TABLE %s CASCADE" % (table,))
        prepare_database(conn, BASE_SQL)

