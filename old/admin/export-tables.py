#!/usr/bin/env python

import ConfigParser
import psycopg2
import tarfile
import sys
import os
from xml.etree import ElementTree

TABLES = [
    ("account", "SELECT id, 'account' || id::text, 'apikey' || id::text, '', anonymous, created, lastlogin, submission_count FROM account"),
    ("account_stats_control", None),
    #("account_openid", None),
    ("application", None),
    ("format", None),
    ("source", None),
    ("fingerprint", None),
    ("track", None),
    ("track_mbid", None),
    #("submission", None),
    ("stats", None),
]

config = ElementTree.parse(sys.argv[1])

opts = {}
for elem in config.find('database'):
    name = elem.tag.lower()
    if name == 'name':
        name = 'database'
    value = elem.text
    opts[name] = value
db = psycopg2.connect(**opts)

cursor = db.cursor()
cursor.execute("SET SESSION CHARACTERISTICS AS TRANSACTION ISOLATION LEVEL SERIALIZABLE")

base_path = "/tmp/acoustid-dump"
os.mkdir(base_path)
for table, sql in TABLES:
    path = os.path.join(base_path, table)
    print " * Exporting %s to %s" % (table, path)
    with open(path, 'w') as fileobj:
        if sql is None:
            copy_sql = "COPY %s TO STDOUT" % table
        else:
            copy_sql = "COPY (%s) TO STDOUT" % sql
        cursor.copy_expert(copy_sql, fileobj)
    
