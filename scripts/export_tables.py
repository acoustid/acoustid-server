#!/usr/bin/env python

# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import os
import logging
import skytools
import xml.etree.cElementTree as etree
import psycopg2.extensions
from contextlib import closing
from acoustid.script import run_script
from acoustid.data.track import merge_missing_mbids

logger = logging.getLogger(__name__)


CORE_TABLES = [
    ("fingerprint", None),
    ("format", None),
    ("meta", None),
    ("replication_control", None),
    ("stats", None),
    ("track", None),
    ("track_mbid", None),
    ("track_meta", None),
    ("track_puid", None),
]

PRIVATE_TABLES = [
    #("account", "SELECT id, 'account' || id::text, 'apikey' || id::text, '', anonymous, created, lastlogin, submission_count FROM account"),
    #("application", "SELECT id, 'app' || id::text, '', 'apikey' || id::text, created, active, account_id FROM application"),
    ("fingerprint_source", None),
    ("source", None),
    ("track_mbid_change", None),
    ("track_mbid_source", None),
    ("track_meta_source", None),
    ("track_puid_source", None),
]

MUSICBRAINZ_TABLES = [
    ("acoustid_mb_replication_control", None),
    ("recording_acoustid", None),
]


def export_tables(cursor, name, tables, data_dir):
    base_path = os.path.join(data_dir, name)
    os.mkdir(base_path)
    for table, sql in tables:
        path = os.path.join(base_path, table)
        logger.info("Exporting %s to %s", table, path)
        with open(path, 'w') as fileobj:
            if sql is None:
                copy_sql = "COPY %s TO STDOUT" % table
            else:
                copy_sql = "COPY (%s) TO STDOUT" % sql
            cursor.copy_expert(copy_sql, fileobj)


def main(script, opts, args):
    conn = script.engines['app'].connect()
    conn.detach()
    with closing(conn):
        conn.connection.rollback()
        conn.connection.set_session(psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE)
        cursor = conn.connection.cursor()
        if opts.full:
            export_tables(cursor, 'acoustid-dump', CORE_TABLES, opts.data_dir)
            export_tables(cursor, 'acoustid-musicbrainz-dump', MUSICBRAINZ_TABLES, opts.data_dir)
        conn.connection.commit()

 
def add_options(parser):
    parser.add_option("-d", "--dir", dest="data_dir", default="/tmp/acoustid-export", help="directory")
    parser.add_option("-f", "--full", dest="full", action="store_true",
        default=False, help="full export")


run_script(main, add_options)
