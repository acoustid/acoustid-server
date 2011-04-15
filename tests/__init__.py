# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

import os
import json
import sqlalchemy
import sqlalchemy.pool
from contextlib import closing
from nose.tools import make_decorator, assert_equals
from acoustid.config import Config

config = None
engine = None

SEQUENCES = [
    ('account', 'id'),
    ('application', 'id'),
    ('format', 'id'),
    ('source', 'id'),
    ('track', 'id'),
]

TABLES = [
    'account',
    'application',
    'format',
    'source',
    'track',
    'track_mbid',
    'musicbrainz.artist',
    'musicbrainz.track',
    'musicbrainz.album',
    'musicbrainz.albummeta',
    'musicbrainz.albumjoin',
    'musicbrainz.release_group',
]

BASE_SQL = '''
INSERT INTO account (name, apikey) VALUES ('User 1', 'user1key');
INSERT INTO account (name, apikey) VALUES ('User 2', 'user2key');
INSERT INTO application (name, apikey, version, account_id) VALUES ('App 1', 'app1key', '0.1', 1);
INSERT INTO application (name, apikey, version, account_id) VALUES ('App 2', 'app2key', '0.1', 2);
INSERT INTO format (name) VALUES ('FLAC');
INSERT INTO source (account_id, application_id) VALUES (1, 1);
INSERT INTO source (account_id, application_id) VALUES (2, 2);
INSERT INTO track (id) VALUES (1), (2), (3), (4);
INSERT INTO track_mbid (track_id, mbid) VALUES (1, 'b81f83ee-4da4-11e0-9ed8-0025225356f3');

INSERT INTO musicbrainz.artist (id, name, sortname, gid, page) VALUES
    (1, 'Artist A', 'Artist A', 'a64796c0-4da4-11e0-bf81-0025225356f3', 0);
INSERT INTO musicbrainz.track (id, artist, name, gid, length) VALUES
    (1, 1, 'Track A', 'b81f83ee-4da4-11e0-9ed8-0025225356f3', 123000),
    (2, 1, 'Track B', '6d885000-4dad-11e0-98ed-0025225356f3', 456000);
INSERT INTO musicbrainz.release_group (id, artist, name, gid, page) VALUES
    (1, 1, 'Release Group A', '83a6c956-e340-48be-b604-72bfc28016fc', 0);
INSERT INTO musicbrainz.album (id, artist, name, gid, page, release_group) VALUES
    (1, 1, 'Album A', 'dd6c2cca-a0e9-4cc4-9a5f-7170bd098e23', 0, 1);
INSERT INTO musicbrainz.albummeta (id, tracks) VALUES
    (1, 2);
INSERT INTO musicbrainz.albumjoin (album, track, sequence) VALUES
    (1, 1, 1), (1, 2, 2);
'''

def prepare_database(conn, sql, params=None):
    with conn.begin():
        for table, column in SEQUENCES:
            conn.execute("""
                SELECT setval('%(table)s_%(column)s_seq',
                    coalesce((SELECT max(%(column)s) FROM %(table)s), 0) + 1, false)
            """ % {'table': table, 'column': column})
        conn.execute(sql, params)
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


def assert_json_equals(expected, actual):
    assert_equals(expected, json.loads(actual))

