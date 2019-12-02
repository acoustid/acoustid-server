# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from typing import Optional, Dict, Any
from sqlalchemy import sql
from acoustid import tables as schema
from acoustid.db import AppDB

logger = logging.getLogger(__name__)


def get_source(conn, id):
    # type: (AppDB, int) -> Optional[Dict[Any, Any]]
    query = sql.select([
        schema.source.c.account_id,
        schema.source.c.application_id,
        schema.source.c.version,
    ], schema.source.c.id == id)
    return conn.execute(query).first()


def find_or_insert_source(conn, application_id, account_id, version=None):
    # type: (AppDB, int, int, Optional[str]) -> int
    """
    Find a source in the database, create it if it doesn't exist yet.
    """
    query = sql.select([schema.source.c.id],
        sql.and_(schema.source.c.account_id == account_id,
                 schema.source.c.application_id == application_id,
                 schema.source.c.version == version))
    id = conn.execute(query).scalar()
    if id is None:
        insert_stmt = schema.source.insert().values(
            account_id=account_id,
            application_id=application_id,
            version=version,
        )
        id = conn.execute(insert_stmt).inserted_primary_key[0]
        logger.info("Inserted source %d with account %d and application %d (%s)", id, account_id, application_id, version)
    return id
