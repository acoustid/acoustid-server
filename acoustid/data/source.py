# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from typing import Any

from sqlalchemy import sql

from acoustid import tables as schema
from acoustid.db import AppDB

logger = logging.getLogger(__name__)


def get_source(conn: AppDB, id: int) -> dict[str, Any] | None:
    query = sql.select(
        schema.source.c.account_id,
        schema.source.c.application_id,
        schema.source.c.version,
    ).where(schema.source.c.id == id)
    source = conn.execute(query).first()
    if source is None:
        return None
    # TODO return Row
    return dict(source._mapping)


def find_or_insert_source(
    conn: AppDB, application_id: int, account_id: int, version: str | None = None
) -> int:
    """
    Find a source in the database, create it if it doesn't exist yet.
    """
    query = sql.select(schema.source.c.id).where(
        sql.and_(
            schema.source.c.account_id == account_id,
            schema.source.c.application_id == application_id,
            schema.source.c.version == version,
        )
    )
    id = conn.execute(query).scalar()
    if id is None:
        insert_stmt = schema.source.insert().values(
            account_id=account_id,
            application_id=application_id,
            version=version,
        )
        id = conn.execute(insert_stmt).inserted_primary_key[0]
        logger.info(
            "Inserted source %d with account %d and application %d (%s)",
            id,
            account_id,
            application_id,
            version,
        )
    return id
