#!/usr/bin/env python

# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import os
import logging
from acoustid.script import run_script
from acoustid.data.track import merge_missing_mbids

logger = logging.getLogger(__name__)


TABLES = [
    ("account", "SELECT id, 'account' || id::text, 'apikey' || id::text, '', anonymous, created, lastlogin, submission_count FROM account"),
    ("account_stats_control", None),
    ("application", "SELECT id, 'app' || id::text, '', 'apikey' || id::text, created, active, account_id FROM application"),
    ("fingerprint", None),
    ("format", None),
    ("meta", None),
    ("source", None),
    ("stats", None),
    ("stats_top_accounts", None),
    ("track", None),
    ("track_mbid", None),
]

def export_tables(cursor):
    cursor.execute("SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    base_path = "/tmp/acoustid-dump"
    os.mkdir(base_path)
    for table, sql in TABLES:
        path = os.path.join(base_path, table)
        logger.info("Exporting %s to %s", table, path)
        with open(path, 'w') as fileobj:
            if sql is None:
                copy_sql = "COPY %s TO STDOUT" % table
            else:
                copy_sql = "COPY (%s) TO STDOUT" % sql
            cursor.copy_expert(copy_sql, fileobj)


def main(script, opts, args):
    conn = script.engine.connect()
    cursor = conn.engine.raw_connection().cursor()
    export_tables(cursor)

run_script(main)

