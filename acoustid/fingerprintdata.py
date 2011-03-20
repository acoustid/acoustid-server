# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

import logging
import chromaprint
from sqlalchemy import sql
from acoustid import tables as schema

logger = logging.getLogger(__name__)


class FingerprintData(object):

    MAX_LENGTH_DIFF = 7
    QUERY_SIZE = 120
    PARTS = ((100, 20), (1, 100))
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

    def __init__(self, db):
        self._db = db

    def search(self, fp, length, good_enough_score, min_score):
        matched = []
        best_score = 0.0
        for part_start, part_length in self.PARTS:
            logger.info("Searching for %i:%i", part_start, part_start + part_length - 1)
            result = self._db.execute(self.PART_SEARCH_SQL, dict(fp=fp, length=length,
                part_start=part_start, part_length=part_length,
                max_length_diff=self.MAX_LENGTH_DIFF, min_score=min_score))
            try:
                for row in result:
                    matched.append(row)
                    if row['score'] >= best_score:
                        best_score = row['score']
            finally:
                result.close()
            if best_score > good_enough_score:
                break
        return matched


