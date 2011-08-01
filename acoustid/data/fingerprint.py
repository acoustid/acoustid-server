# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
import chromaprint
from contextlib import closing
from sqlalchemy import sql
from acoustid import tables as schema

logger = logging.getLogger(__name__)


FINGERPRINT_VERSION = 1
MAX_LENGTH_DIFF = 7
PARTS = ((1, 20), (21, 100))
PART_SEARCH_SQL = """
SELECT id, track_id, score FROM (
    SELECT id, track_id, acoustid_compare(fingerprint, query) AS score
    FROM fingerprint, (SELECT %(fp)s::int4[] AS query) q
    WHERE
        length BETWEEN %(length)s - %(max_length_diff)s AND %(length)s + %(max_length_diff)s AND
        subarray(acoustid_extract_query(query), %(part_start)s, %(part_length)s) && acoustid_extract_query(fingerprint)
) f WHERE score > %(min_score)s ORDER BY score DESC, id
"""


def decode_fingerprint(fingerprint_string):
    """Decode a compressed and base64-encoded fingerprint"""
    fingerprint, version = chromaprint.decode_fingerprint(fingerprint_string)
    if version == FINGERPRINT_VERSION:
        return fingerprint


def lookup_fingerprint(conn, fp, length, good_enough_score, min_score, fast=False):
    """Search for a fingerprint in the database"""
    matched = []
    best_score = 0.0
    for part_start, part_length in PARTS:
        params = dict(fp=fp, length=length, part_start=part_start,
            part_length=part_length, max_length_diff=MAX_LENGTH_DIFF,
            min_score=min_score)
        with closing(conn.execute(PART_SEARCH_SQL, params)) as result:
            for row in result:
                matched.append(row)
                if row['score'] >= best_score:
                    best_score = row['score']
        if best_score > good_enough_score:
            break
    return matched


def insert_fingerprint(conn, data, submission_id=None, source_id=None):
    """
    Insert a new fingerprint into the database
    """
    with conn.begin():
        insert_stmt = schema.fingerprint.insert().values({
            'fingerprint': data['fingerprint'],
            'length': data['length'],
            'bitrate': data.get('bitrate'),
            'format_id': data.get('format_id'),
            'track_id': data['track_id'],
            'meta_id': data.get('meta_id'),
            'submission_count': 1,
        })
        id = conn.execute(insert_stmt).inserted_primary_key[0]
        if submission_id and source_id:
            insert_stmt = schema.fingerprint_source.insert().values({
                'fingerprint_id': id,
                'submission_id': submission_id,
                'source_id': source_id,
            })
            conn.execute(insert_stmt)
    logger.debug("Inserted fingerprint %r with data %r", id, data)
    return id


def inc_fingerprint_submission_count(conn, id):
    update_stmt = schema.fingerprint.update().where(schema.fingerprint.c.id == id)
    conn.execute(update_stmt.values(submission_count=sql.text('submission_count+1')))
    return True


