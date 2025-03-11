# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from typing import Any

from sqlalchemy import sql

from acoustid import tables as schema
from acoustid.db import AppDB
from acoustid.utils import generate_api_key

logger = logging.getLogger(__name__)


def lookup_account_id_by_name(conn: AppDB, name: str) -> int | None:
    query = sql.select(schema.account.c.id).where(schema.account.c.name == name)
    return conn.execute(query).scalar()


def lookup_account_id_by_apikey(conn: AppDB, apikey: str) -> int | None:
    query = sql.select(schema.account.c.id).where(schema.account.c.apikey == apikey)
    return conn.execute(query).scalar()


def lookup_account_id_by_mbuser(conn: AppDB, mbuser: str) -> int | None:
    query = sql.select(schema.account.c.id).where(
        sql.func.lower(schema.account.c.mbuser) == sql.func.lower(mbuser)
    )
    return conn.execute(query).scalar()


def lookup_account_id_by_openid(conn: AppDB, openid: str) -> int | None:
    query = sql.select(schema.account_openid.c.account_id).where(
        schema.account_openid.c.openid == openid
    )
    return conn.execute(query).scalar()


def get_account_details(conn: AppDB, id: int) -> dict[str, Any] | None:
    query = sql.select(schema.account).where(schema.account.c.id == id)
    row = conn.execute(query).fetchone()
    return dict(row) if row else None


def get_account_details_by_mbuser(conn: AppDB, mbuser: str) -> dict[dict, Any] | None:
    query = sql.select(schema.account).where(
        sql.func.lower(schema.account.c.mbuser) == sql.func.lower(mbuser)
    )
    row = conn.execute(query).fetchone()
    return dict(row) if row else None


def update_account_lastlogin(conn: AppDB, id: int) -> None:
    update_stmt = schema.account.update().where(schema.account.c.id == id)
    update_stmt = update_stmt.values(lastlogin=sql.text("now()"))
    conn.execute(update_stmt)


def insert_account(conn: AppDB, data: dict[str, Any]) -> tuple[int, str]:
    """
    Insert a new account into the database
    """
    insert_stmt = (
        schema.account.insert()
        .values(
            {
                "name": data["name"],
                "mbuser": data.get("mbuser"),
                "created_from": data.get("created_from"),
                "application_id": data.get("application_id"),
                "application_version": data.get("application_version"),
                "lastlogin": sql.text("now()"),
                "apikey": generate_api_key(),
            }
        )
        .returning(schema.account.c.id, schema.account.c.apikey)
    )
    row = conn.execute(insert_stmt).fetchone()
    if row is None:
        raise Exception("Failed to insert account")

    if "openid" in data:
        insert_openid_stmt = schema.account_openid.insert().values(
            {
                "account_id": row.id,
                "openid": data["openid"],
            }
        )
        conn.execute(insert_openid_stmt)
    logger.debug("Inserted account %r with data %r", row.id, data)
    return row.id, row.api_key


def reset_account_apikey(conn: AppDB, id: int) -> None:
    update_stmt = schema.account.update().where(schema.account.c.id == id)
    update_stmt = update_stmt.values(apikey=generate_api_key())
    conn.execute(update_stmt)
    logger.debug("Reset API key for account %r", id)


def is_moderator(conn: AppDB, id: int) -> bool:
    query = sql.select(schema.account.c.mbuser).where(schema.account.c.id == id)
    return bool(conn.execute(query).scalar())
