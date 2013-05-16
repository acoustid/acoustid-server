# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import time
import logging
import chromaprint
from contextlib import closing
from sqlalchemy import sql
from acoustid import tables as schema, const
from acoustid.indexclient import IndexClientError

logger = logging.getLogger(__name__)


FINGERPRINT_VERSION = 1
PARTS = ((1, 20), (21, 100))
PART_SEARCH_SQL = """
SELECT f.id, f.track_id, t.gid AS track_gid, score FROM (
    SELECT id, track_id, acoustid_compare2(fingerprint, query, %(max_offset)s) AS score
    FROM fingerprint, (SELECT %(fp)s::int4[] AS query) q
    WHERE
        length BETWEEN %(length)s - %(max_length_diff)s AND %(length)s + %(max_length_diff)s AND
        subarray(acoustid_extract_query(query), %(part_start)s, %(part_length)s) && acoustid_extract_query(fingerprint)
) f JOIN track t ON f.track_id=t.id WHERE f.score > %(min_score)s ORDER BY f.score DESC, f.id
"""


def decode_fingerprint(fingerprint_string):
    """Decode a compressed and base64-encoded fingerprint"""
    fingerprint, version = chromaprint.decode_fingerprint(fingerprint_string)
    if version == FINGERPRINT_VERSION:
        return fingerprint


def lookup_fingerprint(conn, fp, length, good_enough_score, min_score, fast=False, max_offset=0):
    """Search for a fingerprint in the database"""
    matched = []
    best_score = 0.0
    for part_start, part_length in PARTS:
        params = dict(fp=fp, length=length, part_start=part_start,
            part_length=part_length, max_length_diff=const.FINGERPRINT_MAX_LENGTH_DIFF,
            min_score=min_score, max_offset=max_offset)
        with closing(conn.execute(PART_SEARCH_SQL, params)) as result:
            for row in result:
                matched.append(row)
                if row['score'] >= best_score:
                    best_score = row['score']
        if best_score > good_enough_score:
            break
    return matched


class FingerprintSearcher(object):

    def __init__(self, db, idx=None, fast=True):
        self.db = db
        self.idx = idx
        self.min_score = const.TRACK_GROUP_MERGE_THRESHOLD
        self.max_length_diff = const.FINGERPRINT_MAX_LENGTH_DIFF
        self.max_offset = const.TRACK_MAX_OFFSET
        self.fast = fast

    def _create_search_query(self, fp, length, condition):
        # construct the subquery
        f_columns = [
            schema.fingerprint.c.id,
            schema.fingerprint.c.track_id,
            sql.func.acoustid_compare2(schema.fingerprint.c.fingerprint, fp,
                                       self.max_offset).label('score'),
        ]
        f_where = sql.and_(
            condition,
            schema.fingerprint.c.length.between(length - self.max_length_diff,
                                                length + self.max_length_diff))
        f = sql.select(f_columns, f_where).alias('f')
        # construct the main query
        columns = [f.c.id, f.c.track_id, schema.track.c.gid.label('track_gid'), f.c.score]
        src = f.join(schema.track, schema.track.c.id == f.c.track_id)
        return sql.select(columns, f.c.score > self.min_score, src,
                           order_by=[f.c.score.desc(), f.c.id])

    def _search_index(self, fp, length):
        # index search
        fp_query = self.db.execute(sql.select([sql.func.acoustid_extract_query(fp)])).scalar()
        if not fp_query:
            return []
        with closing(self.idx.connect()) as idx:
            results = idx.search(fp_query)
            if not results:
                return []
            min_score = results[0].score * 0.1 # at least 10% of the top score
            candidate_ids = [r.id for r in results if r.score > min_score]
            if not candidate_ids:
                return []
        # construct the query
        condition = schema.fingerprint.c.id.in_(candidate_ids)
        query = self._create_search_query(fp, length, condition)
        # database scoring
        matches = self.db.execute(query).fetchall()
        return matches

    def _search_database(self, fp, length, min_fp_id):
        # construct the query
        condition = sql.func.acoustid_extract_query(schema.fingerprint.c.fingerprint).op('&&')(sql.func.acoustid_extract_query(fp))
        if min_fp_id:
            condition = sql.and_(condition, schema.fingerprint.c.id > min_fp_id)
        query = self._create_search_query(fp, length, condition)
        # database scoring
        matches = self.db.execute(query).fetchall()
        return matches

    def _get_min_indexed_fp_id(self):
        if self.idx is None:
            return 0
        with closing(self.idx.connect()) as idx:
            return int(idx.get_attribute('max_document_id') or '0')

    def search(self, fp, length):
        min_fp_id = 0 if self.idx is None or self.fast else self._get_min_indexed_fp_id()
        matches = None
        if self.idx is not None:
            try:
                matches = self._search_index(fp, length)
            except IndexClientError:
                logger.exception("Index search error")
                matches = None
        if not self.fast and not matches:
            matches = self._search_database(fp, length, min_fp_id)
        return matches or []


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
    logger.debug("Inserted fingerprint %r", id)
    return id


def inc_fingerprint_submission_count(conn, id, submission_id=None, source_id=None):
    update_stmt = schema.fingerprint.update().where(schema.fingerprint.c.id == id)
    conn.execute(update_stmt.values(submission_count=sql.text('submission_count+1')))
    if submission_id and source_id:
        insert_stmt = schema.fingerprint_source.insert().values({
            'fingerprint_id': id,
            'submission_id': submission_id,
            'source_id': source_id,
        })
        conn.execute(insert_stmt)
    return True


def update_fingerprint_index(db, index, limit=1000):
    with closing(index.connect()) as index:
        max_id = int(index.get_attribute('max_document_id') or '0')
        query = sql.select([
            schema.fingerprint.c.id,
            sql.func.acoustid_extract_query(schema.fingerprint.c.fingerprint),
        ]).where(schema.fingerprint.c.id > max_id).\
            order_by(schema.fingerprint.c.id).limit(limit)
        in_transaction = False
        for id, fingerprint in db.execute(query):
            if not in_transaction:
                index.begin()
                in_transaction = True
            logger.debug("Adding fingerprint %s to index %s", id, index)
            index.insert(id, fingerprint)
        if in_transaction:
            index.commit()

