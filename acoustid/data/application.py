# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from typing import Any, Dict, List, Tuple

from sqlalchemy import sql

from acoustid import tables as schema
from acoustid.db import AppDB
from acoustid.utils import generate_api_key

logger = logging.getLogger(__name__)


def lookup_application_id_by_apikey(conn, apikey, only_active=False):
    # type: (AppDB, str, bool) -> int
    query = sql.select([schema.application.c.id], schema.application.c.apikey == apikey)
    if only_active:
        query = query.where(schema.application.c.active.is_(True))
    return conn.execute(query).scalar()


def lookup_application_id(conn, application_id, account_id=None):
    # type: (AppDB, str, int | None) -> int
    query = sql.select(
        [schema.application.c.id], schema.application.c.id == application_id
    )
    if account_id is not None:
        query = query.where(schema.application.c.account_id == account_id)
    return conn.execute(query).scalar()


def find_applications_by_account(conn, account_id):
    # type: (AppDB, int) -> List[Dict[Any, Any]]
    query = schema.application.select(schema.application.c.account_id == account_id)
    query = query.order_by(schema.application.c.name)
    return [dict(i) for i in conn.execute(query).fetchall()]


def find_applications_by_apikeys(conn, apikeys):
    # type: (AppDB, List[str]) -> List[Dict[Any, Any]]
    query = schema.application.select(schema.application.c.apikey.in_(apikeys))
    return [dict(i) for i in conn.execute(query).fetchall()]


def insert_application(conn, data):
    # type: (AppDB, Dict[str, Any]) -> Tuple[int, str]
    """
    Insert a new application into the database
    """
    api_key = generate_api_key()
    insert_stmt = schema.application.insert().values(
        {
            "name": data["name"],
            "version": data["version"],
            "email": data.get("email"),
            "website": data.get("website"),
            "account_id": data["account_id"],
            "apikey": api_key,
        }
    )
    id = conn.execute(insert_stmt).inserted_primary_key[0]
    logger.debug("Inserted application %r with data %r", id, data)
    return id, api_key


def update_application(conn, id, data):
    # type: (AppDB, int, Dict[str, Any]) -> int
    update_stmt = schema.application.update().where(schema.application.c.id == id)
    update_stmt = update_stmt.values(
        {
            "name": data["name"],
            "version": data["version"] or None,
            "email": data.get("email") or None,
            "website": data.get("website") or None,
        }
    )
    conn.execute(update_stmt)
    logger.debug("Updated application %r with data %r", id, data)
    return id


def update_application_status(conn, id, active):
    # type: (AppDB, int, bool) -> int
    data = {"active": active}
    update_stmt = schema.application.update().where(schema.application.c.id == id)
    update_stmt = update_stmt.values(data)
    conn.execute(update_stmt)
    logger.debug("Updated application %r with data %r", id, data)
    return id
