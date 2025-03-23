# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from typing import Any

from sqlalchemy import RowMapping, sql
from sqlalchemy.dialects.postgresql import insert

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
    return dict(source._mapping) if source is not None else None


def find_source_id(
    conn: AppDB,
    application_id: int,
    account_id: int,
    version: str | None = None,
) -> int | None:
    query = sql.select(
        schema.source.c.id,
    ).where(
        sql.and_(
            schema.source.c.account_id == account_id,
            schema.source.c.application_id == application_id,
            schema.source.c.version == version,
        )
    )
    return conn.execute(query).scalar()


def find_or_insert_source(
    conn: AppDB,
    application_id: int,
    account_id: int,
    version: str | None = None,
) -> int:
    """
    Find a source in the database, create it if it doesn't exist yet.
    """
    retries = 3
    while True:
        source_id = find_source_id(conn, application_id, account_id, version)
        if source_id is not None:
            return source_id

        insert_stmt = (
            insert(schema.source)
            .values(
                account_id=account_id,
                application_id=application_id,
                version=version,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    schema.source.c.account_id,
                    schema.source.c.application_id,
                    schema.source.c.version,
                ],
            )
            .returning(schema.source.c.id)
        )
        source_id = conn.execute(insert_stmt).scalar()

        # If insert returned non-NULL source_id, we're done
        if source_id is not None:
            logger.info(
                "Inserted source %d with account %d and application %d (%s)",
                source_id,
                account_id,
                application_id,
                version,
            )
            return source_id

        # If insert returned NULL, it means there was a conflict, so we need to query again
        retries -= 1
        if retries == 0:
            raise RuntimeError("Failed to insert source")
