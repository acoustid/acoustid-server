# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables as schema

logger = logging.getLogger(__name__)


def find_or_insert_format(conn, name):
    """
    Find a format in the database, create it if it doesn't exist yet.
    """
    with conn.begin():
        query = sql.select([schema.format.c.id], schema.format.c.name == name)
        id = conn.execute(query).scalar()
        if id is None:
            insert_stmt = schema.format.insert().values(name=name)
            id = conn.execute(insert_stmt).inserted_primary_key[0]
            logger.info("Inserted format %d with name %s", id, name)
    return id

