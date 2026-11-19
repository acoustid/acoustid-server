# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from typing import Any

from sqlalchemy import sql

from acoustid import tables as schema
from acoustid.db import AppDB
from acoustid.utils import generate_api_key

logger = logging.getLogger(__name__)


def lookup_application_id_by_apikey(
    conn: AppDB, apikey: str, only_active: bool = False
) -> int | None:
    query = sql.select(schema.application.c.id).where(
        schema.application.c.apikey == apikey
    )
    if only_active:
        query = query.where(schema.application.c.active.is_(True))
    return conn.execute(query).scalar()


def lookup_application_requires_user_key(conn: AppDB, application_id: int) -> bool:
    """Whether lookups with this application's key must carry a user key.

    Keyed on the id rather than the API key so it can be cached separately
    from check_app_api_key, which is being changed elsewhere. Applications are
    few and the result is cached per id, so this is about one extra query per
    application per minute rather than one per request.

    Unknown ids answer True: an application that cannot be read should not
    thereby become exempt.
    """
    query = sql.select(schema.application.c.requires_user_key).where(
        schema.application.c.id == application_id
    )
    value = conn.execute(query).scalar()
    return True if value is None else bool(value)


def lookup_application_id(
    conn: AppDB, application_id: str, account_id: int | None = None
) -> int | None:
    query = sql.select(schema.application.c.id).where(
        schema.application.c.id == application_id
    )
    if account_id is not None:
        query = query.where(schema.application.c.account_id == account_id)
    return conn.execute(query).scalar()


def find_applications_by_account(conn: AppDB, account_id: int) -> list[dict[str, Any]]:
    query = sql.select(schema.application).where(
        schema.application.c.account_id == account_id
    )
    query = query.order_by(schema.application.c.name)
    return [dict(i._mapping) for i in conn.execute(query).fetchall()]


def find_applications_by_apikeys(
    conn: AppDB, apikeys: list[str]
) -> list[dict[str, Any]]:
    query = sql.select(schema.application).where(
        schema.application.c.apikey.in_(apikeys)
    )
    return [dict(i._mapping) for i in conn.execute(query).fetchall()]


def insert_application(conn: AppDB, data: dict[str, Any]) -> tuple[int, str]:
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
    if "requires_user_key" in data:
        insert_stmt = insert_stmt.values(requires_user_key=data["requires_user_key"])
    id = conn.execute(insert_stmt).inserted_primary_key[0]
    logger.debug("Inserted application %r with data %r", id, data)
    return id, api_key


def update_application(conn: AppDB, id: int, data: dict[str, Any]) -> int:
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


def update_application_status(
    conn: AppDB, id: int, active: bool, requires_user_key: bool | None = None
) -> int:
    data: dict[str, Any] = {"active": active}
    # Left alone when not given, rather than defaulted. The caller that drives
    # this is acoustid.biz's hourly key sync, which has always sent only
    # `active`; defaulting here would have every one of those runs silently
    # reset the flag on every application it touches.
    if requires_user_key is not None:
        data["requires_user_key"] = requires_user_key
    update_stmt = schema.application.update().where(schema.application.c.id == id)
    update_stmt = update_stmt.values(data)
    conn.execute(update_stmt)
    logger.debug("Updated application %r with data %r", id, data)
    return id
