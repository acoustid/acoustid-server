# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

import logging
from sqlalchemy import sql
from acoustid import tables as schema

logger = logging.getLogger(__name__)


def insert_submission(conn, data):
    """
    Insert a new submission into the database.
    """
    with conn.begin():
        insert_stmt = schema.submission.insert().values({
            'fingerprint': data['fingerprint'],
            'length': data['length'],
            'bitrate': data.get('bitrate'),
            'source_id': data['source_id'],
            'mbid': data.get('mbid'),
            'puid': data.get('puid'),
            'format_id': data.get('format_id'),
        })
        id = conn.execute(insert_stmt).inserted_primary_key[0]
    logger.info("Inserted submission %r with data %r", id, data)

