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
        length BETWEEN %(length)s - %(max_length_diff)s AND %(length)s + %(max_length_diff)s AND (
            (%(length)s >= 34 AND subarray(extract_fp_query(query), %(part_start)s, %(part_length)s)
                               && extract_fp_query(fingerprint)) OR
            (%(length)s <= 50 AND subarray(extract_short_fp_query(query), %(part_start)s, %(part_length)s)
                               && extract_short_fp_query(fingerprint))
        )
) f WHERE score > %(min_score)s ORDER BY score DESC
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


def insert_fingerprint(conn, data):
    """
    Insert a new fingerprint into the database
    """
    with conn.begin():
        insert_stmt = schema.fingerprint.insert().values({
            'fingerprint': data['fingerprint'],
            'length': data['length'],
            'bitrate': data.get('bitrate'),
            'source_id': data['source_id'],
            'format_id': data.get('format_id'),
            'track_id': data['track_id'],
        })
        id = conn.execute(insert_stmt).inserted_primary_key[0]
    logger.debug("Inserted fingerprint %r with data %r", id, data)
    return id

