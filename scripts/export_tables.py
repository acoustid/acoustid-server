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
    #("account_stats_control", None),
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


def export_tables(cursor, name, tables):
    base_path = os.path.join("/tmp/acoustid-export", name)
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


def dump_colums(root, root_name, columns):
    if columns:
        node = etree.SubElement(root, root_name)
        for name, value in columns.iteritems():
            column_node = etree.SubElement(node, 'column')
            column_node.attrib['name'] = name
            if value is None:
                column_node.attrib['null'] = 'yes'
            else:
                column_node.text = value.decode('UTF-8')


def create_musicbrainz_replication_packet(cursor):
    cursor.execute("""
        UPDATE acoustid_mb_replication_control
        SET current_replication_sequence = current_replication_sequence + 1,
            last_replication_date = now()
        RETURNING current_schema_sequence, current_replication_sequence""")
    schema_seq, replication_seq = cursor.fetchone()
    cursor.execute("""
        SELECT * FROM mirror_queue
        WHERE tblname IN ('recording_acoustid', 'acoustid_mb_replication_control')
        ORDER BY txid, id""")
    packet_node = etree.Element('packet')
    packet_node.attrib['schema_seq'] = str(schema_seq)
    packet_node.attrib['replication_seq'] = str(replication_seq)
    transaction_node = None
    transaction_id = None
    for seqid, txid, table, operation, data in cursor:
        if transaction_id is None or transaction_id != txid:
            transaction_node = etree.SubElement(packet_node, 'transaction')
            transaction_node.attrib['id'] = str(txid)
            transaction_id = txid
        event_node = etree.SubElement(transaction_node, 'event')
        event_node.attrib['table'] = table
        event_node.attrib['op'] = operation
        event_node.attrib['id'] = str(seqid)
        keys, values = skytools.parse_logtriga_sql(operation, data.encode('UTF-8'), splitkeys=True)
	dump_colums(event_node, 'keys', keys)
	dump_colums(event_node, 'values', values)
    fp = open('/tmp/acoustid-export/acoustid-musicbrainz-update-%d.xml' % replication_seq, 'w')
    fp.write(etree.tostring(packet_node, encoding="UTF-8"))
    fp.flush()
    os.fsync(fp.fileno())
    fp.close()


def create_replication_packet(cursor):
    cursor.execute("""
        UPDATE replication_control
        SET current_replication_sequence = current_replication_sequence + 1,
            last_replication_date = now()
        RETURNING current_schema_sequence, current_replication_sequence""")
    schema_seq, replication_seq = cursor.fetchone()
    cursor.execute("""
        SELECT * FROM mirror_queue
        WHERE tblname NOT IN ('recording_acoustid', 'acoustid_mb_replication_control')
        ORDER BY txid, id""")
    packet_node = etree.Element('packet')
    packet_node.attrib['schema_seq'] = str(schema_seq)
    packet_node.attrib['replication_seq'] = str(replication_seq)
    transaction_node = None
    transaction_id = None
    for seqid, txid, table, operation, data in cursor:
        if transaction_id is None or transaction_id != txid:
            transaction_node = etree.SubElement(packet_node, 'transaction')
            transaction_node.attrib['id'] = str(txid)
            transaction_id = txid
        event_node = etree.SubElement(transaction_node, 'event')
        event_node.attrib['table'] = table
        event_node.attrib['op'] = operation
        event_node.attrib['id'] = str(seqid)
        keys, values = skytools.parse_logtriga_sql(operation, data.encode('UTF-8'), splitkeys=True)
	dump_colums(event_node, 'keys', keys)
	dump_colums(event_node, 'values', values)
    fp = open('/tmp/acoustid-export/acoustid-update-%d.xml' % replication_seq, 'w')
    fp.write(etree.tostring(packet_node, encoding="UTF-8"))
    fp.flush()
    os.fsync(fp.fileno())
    fp.close()


def export_replication(cursor):
    create_replication_packet(cursor)
    create_musicbrainz_replication_packet(cursor)
    cursor.execute("DELETE FROM mirror_queue")


def main(script, opts, args):
    conn = script.engine.connect()
    conn.detach()
    with closing(conn):
        conn.connection.rollback()
        conn.connection.set_session(psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE)
        cursor = conn.connection.cursor()
        export_replication(cursor)
        if opts.full:
            #export_tables(cursor, 'acoustid-dump', CORE_TABLES)
            export_tables(cursor, 'acoustid-musicbrainz-dump', MUSICBRAINZ_TABLES)
        conn.connection.commit()

 
def add_options(parser):
    parser.add_option("-f", "--full", dest="full", action="store_true",
        default=False, help="full export")


run_script(main, add_options)

