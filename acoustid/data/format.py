# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging

from sqlalchemy import sql
from sqlalchemy.dialects.postgresql import insert

from acoustid import tables as schema
from acoustid.db import AppDB

logger = logging.getLogger(__name__)


def find_or_insert_format(conn: AppDB, name: str) -> int:
    """
    Find a format in the database, create it if it doesn't exist yet.
    """
    query = sql.select(schema.format.c.id).where(schema.format.c.name == name)
    id = conn.execute(query).scalar()
    if id is not None:
        return id

    # Two importers can both miss the select above for a name neither has seen
    # before, and format_idx_name is unique, so the second insert used to raise
    # and take the whole import pass down with it. That became reachable when
    # the importer went from one replica to three.
    insert_stmt = (
        insert(schema.format)
        .values(name=name)
        .on_conflict_do_nothing(index_elements=[schema.format.c.name])
        .returning(schema.format.c.id)
    )
    id = conn.execute(insert_stmt).scalar()
    if id is None:
        # The conflict fired, so somebody inserted it in between. Theirs is as
        # good as ours would have been.
        #
        # scalar_one() rather than scalar(): returning no row here implies a
        # committed conflicting row, so the re-select cannot come up empty. If
        # the other transaction were still open our insert would be waiting on
        # the unique index instead of arriving here, and if it then rolled back
        # our insert would have succeeded and returned an id.
        #
        # That argument needs READ COMMITTED, which is what the server gives us
        # -- nothing in create_engine_params sets an isolation level. Under
        # REPEATABLE READ the re-select would read a snapshot older than the
        # other transaction's commit, find nothing, and raise here instead.
        id = conn.execute(query).scalar_one()
        return id

    logger.info("Inserted format %d with name %s", id, name)
    return id
