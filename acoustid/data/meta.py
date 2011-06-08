# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables as schema

logger = logging.getLogger(__name__)


def insert_meta(conn, values):
    with conn.begin():
        insert_stmt = schema.meta.insert().values(**values)
        id = conn.execute(insert_stmt).inserted_primary_key[0]
        logger.debug("Inserted meta %d with values %r", id, values)
    return id

