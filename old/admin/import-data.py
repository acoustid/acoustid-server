#!/usr/bin/env python

import psycopg2
import os
import sys

conn = psycopg2.connect("host=127.0.0.1 dbname=fp user=postgres")

def signed_32b_int(i):
    if i & 0x80000000:
        return i - 0x100000000
    return i


def reader(input):
    group = {}
    for line in input:
        line = line.strip()
        if not line:
            if group:
                yield group
            group = {}
            continue
        name, value = line.split('=', 1)
        group[name] = value
    if group:
        yield group


def insert_source(conn, name):
    c = conn.cursor()
    c.execute("INSERT INTO source (name) VALUES (%s) RETURNING id", (name,))
    return c.fetchone()[0]


def import_file(conn, source_id, name):
    c = conn.cursor()
    i = 0
    for entry in reader(open(name)):
        i += 1
        if 'FINGERPRINT' not in entry:
            continue
        length = int(entry['LENGTH'])
        if length > 0x7FFF:
            continue
        bitrate = int(entry['BITRATE'])
        fingerprint = [signed_32b_int(int(x, 16)) for x in entry['FINGERPRINT'].split()]
        if not fingerprint:
            continue
        metadata_id = None
        if entry['ARTIST'] or entry['TITLE'] or entry['ALBUM']:
            c.execute("INSERT INTO metadata (title, album, artist) VALUES (%s, %s, %s) RETURNING id", (
                entry['TITLE'],
                entry['ALBUM'],
                entry['ARTIST'],
            ))
            metadata_id = c.fetchone()[0]
        try:
            c.execute("INSERT INTO fingerprint (length, bitrate, fingerprint, source_id) VALUES (%s, %s, %s, %s) RETURNING id", (length, bitrate, fingerprint, source_id))
        except psycopg2.DataError, e:
            print e
            continue
        fingerprint_id = c.fetchone()[0]
        try:
            c.execute("INSERT INTO fingerprint_query (id, length, fingerprint) VALUES (%s, %s, %s)", (fingerprint_id, length, fingerprint[:463]))
        except psycopg2.DataError, e:
            print e
            continue
        if metadata_id:
            c.execute("INSERT INTO fingerprint_metadata (fingerprint_id, metadata_id) VALUES (%s, %s)", (fingerprint_id, metadata_id))
        print i, '\r',
        sys.stdout.flush()
    conn.commit()

source_id = insert_source(conn, 'Import')
for name in sys.argv[1:]:
    print name
    import_file(conn, source_id, name)

