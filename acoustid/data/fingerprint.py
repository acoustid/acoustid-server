# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from typing import Dict, Any, Optional, List, NamedTuple
from sqlalchemy import sql
from acoustid import tables as schema, const, chromaprint
from acoustid.indexclient import Index, IndexClientPool, IndexClientError
from acoustid.db import FingerprintDB, IngestDB

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
    # type: (str) -> Optional[List[int]]
    """Decode a compressed and base64-encoded fingerprint"""
    try:
        fingerprint, version = chromaprint.decode_fingerprint(fingerprint_string)
    except chromaprint.FingerprintError:
        return None
    if version != FINGERPRINT_VERSION:
        return None
    return fingerprint


FingerprintMatch = NamedTuple('FingerprintMatch', [('fingerprint_id', int), ('track_id', int), ('track_gid', str), ('score', float)])


class FingerprintSearcher(object):

    def __init__(self, db, index_pool, fast=True):
        # type: (FingerprintDB, IndexClientPool, bool) -> None
        self.db = db
        self.index_pool = index_pool
        self.min_score = const.TRACK_GROUP_MERGE_THRESHOLD
        self.max_length_diff = const.FINGERPRINT_MAX_LENGTH_DIFF
        self.max_offset = const.TRACK_MAX_OFFSET
        self.fast = fast

    def _create_search_query(self, fp, length, condition, max_results):
        # type: (List[int], int, Any, Optional[int]) -> Any
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
        query = sql.select(columns, f.c.score > self.min_score, src,
                           order_by=[f.c.score.desc(), f.c.id])
        if max_results:
            query = query.limit(max_results)
        return query

    def _search_index(self, fp, length, index, max_candidates=None, min_score_pct=None):
        # type: (List[int], int, Index, Optional[int], Optional[float]) -> Optional[sql.ClauseElement]
        # index search
        fp_query = self.db.execute(sql.select([sql.func.acoustid_extract_query(fp)])).scalar()
        if not fp_query:
            return None
        results = index.search(fp_query)
        if not results:
            return None

        results.sort(key=lambda r: -r.score)

        if min_score_pct is not None:
            min_score = results[0].score * min_score_pct / 100
            results = [r for r in results if r.score > min_score]

        if max_candidates is not None:
            results = results[:max_candidates]

        if not results:
            return None

        candidate_ids = [r.id for r in results]
        condition = schema.fingerprint.c.id.in_(candidate_ids)
        return condition

    def _search_database(self, fp, length, min_fingerprint_id):
        # type: (List[int], int, int) -> Optional[sql.ClauseElement]
        # construct the query
        condition = sql.and_(
            sql.func.acoustid_extract_query(schema.fingerprint.c.fingerprint).op('&&')(sql.func.acoustid_extract_query(fp)),
            schema.fingerprint.c.id > min_fingerprint_id)
        return condition

    def _get_max_indexed_fingerprint_id(self, index):
        # type: (Index) -> int
        return int(index.get_attribute('max_document_id') or '0')

    def search(self, fp, length, max_results=None):
        # type: (List[int], int, Optional[int]) -> List[FingerprintMatch]
        conditions = []

        max_candidates = 100
        min_score_pct = 2.5

        if self.fast:
            max_candidates *= 10
            min_score_pct *= 10

        with self.index_pool.connect() as index:
            if not self.fast:
                max_indexed_fingerprint_id = self._get_max_indexed_fingerprint_id(index)

            try:
                condition = self._search_index(fp, length, index, max_candidates=max_candidates, min_score_pct=min_score_pct)
                if condition is not None:
                    conditions.append(condition)
            except IndexClientError:
                if not self.fast:
                    raise
                logger.exception("Index search error")

        if not self.fast:
            condition = self._search_database(fp, length, max_indexed_fingerprint_id)
            if condition is not None:
                conditions.append(condition)

        if not conditions:
            return []

        query = self._create_search_query(fp, length, sql.or_(*conditions), max_results=max_results)
        matches = [FingerprintMatch(*i) for i in self.db.execute(query)]
        return matches


def insert_fingerprint(fingerprint_db, ingest_db, data, submission_id=None, source_id=None):
    # type: (FingerprintDB, IngestDB, Dict[str, Any], Optional[int], Optional[int]) -> int
    """
    Insert a new fingerprint into the database
    """
    insert_stmt = schema.fingerprint.insert().values({
        'fingerprint': data['fingerprint'],
        'length': data['length'],
        'bitrate': data.get('bitrate'),
        'format_id': data.get('format_id'),
        'track_id': data['track_id'],
        'submission_count': 1,
    })
    fingerprint_id = fingerprint_db.execute(insert_stmt).inserted_primary_key[0]
    if submission_id and source_id:
        insert_stmt = schema.fingerprint_source.insert().values({
            'fingerprint_id': fingerprint_id,
            'submission_id': submission_id,
            'source_id': source_id,
        })
        ingest_db.execute(insert_stmt)
    logger.debug("Inserted fingerprint %r", fingerprint_id)
    return fingerprint_id


def inc_fingerprint_submission_count(fingerprint_db, ingest_db, fingerprint_id, submission_id=None, source_id=None):
    # type: (FingerprintDB, IngestDB, int, Optional[int], Optional[int]) -> None
    update_stmt = schema.fingerprint.update().where(schema.fingerprint.c.id == fingerprint_id)
    fingerprint_db.execute(update_stmt.values(submission_count=sql.text('submission_count+1')))
    if submission_id and source_id:
        insert_stmt = schema.fingerprint_source.insert().values({
            'fingerprint_id': fingerprint_id,
            'submission_id': submission_id,
            'source_id': source_id,
        })
        ingest_db.execute(insert_stmt)


def update_fingerprint_index(fingerprint_db, index, limit=1000):
    # type: (FingerprintDB, Index, int) -> None
    max_id = int(index.get_attribute('max_document_id') or '0')
    last_id = max_id
    query = sql.select([
        schema.fingerprint.c.id,
        sql.func.acoustid_extract_query(schema.fingerprint.c.fingerprint),
    ]).where(schema.fingerprint.c.id > max_id).\
        order_by(schema.fingerprint.c.id).limit(limit)
    in_transaction = False
    for id, fingerprint in fingerprint_db.execute(query):
        if not in_transaction:
            index.begin()
            in_transaction = True
        logger.debug("Adding fingerprint %s to index %s", id, index)
        index.insert(id, fingerprint)
        last_id = id
    if in_transaction:
        index.commit()
        logger.info("Updated index %s up to fingerprint %s", index, last_id)
