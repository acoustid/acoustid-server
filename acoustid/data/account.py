# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
import json
import logging
import re
import secrets
from typing import Any, NamedTuple

import cachetools
from redis import Redis
from sqlalchemy import Date, String, sql
from sqlalchemy.dialects.postgresql import insert

from acoustid import const
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
    return dict(row._mapping) if row else None


def get_account_details_by_mbuser(conn: AppDB, mbuser: str) -> dict[str, Any] | None:
    query = sql.select(schema.account).where(
        sql.func.lower(schema.account.c.mbuser) == sql.func.lower(mbuser)
    )
    row = conn.execute(query).fetchone()
    return dict(row._mapping) if row else None


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
    return row.id, row.apikey


def reset_account_apikey(conn: AppDB, id: int) -> None:
    update_stmt = schema.account.update().where(schema.account.c.id == id)
    update_stmt = update_stmt.values(apikey=generate_api_key())
    conn.execute(update_stmt)
    logger.debug("Reset API key for account %r", id)


def is_moderator(conn: AppDB, id: int) -> bool:
    query = sql.select(schema.account.c.mbuser).where(schema.account.c.id == id)
    return bool(conn.execute(query).scalar())


USER_KEY_PENDING = "pending"
USER_KEY_APPROVED = "approved"
USER_KEY_DECLINED = "declined"
USER_KEY_EXPIRED = "expired"
USER_KEY_REVOKED = "revoked"


class UserKey(NamedTuple):
    account_id: int | None
    # None for account.apikey, which works with any application.
    application_id: int | None
    state: str


def lookup_user_api_key(conn: AppDB, apikey: str) -> UserKey | None:
    """Resolve a user key, either account.apikey or one from the link flow."""
    account = schema.account
    key = schema.account_application_key
    query = (
        sql.union_all(
            sql.select(
                sql.literal(0).label("priority"),
                account.c.id.label("account_id"),
                sql.null().label("application_id"),
                sql.literal(USER_KEY_APPROVED).label("state"),
            ).where(account.c.apikey == apikey),
            sql.select(
                sql.literal(1).label("priority"),
                key.c.account_id,
                key.c.application_id,
                sql.case(
                    (key.c.revoked.is_not(None), USER_KEY_REVOKED),
                    (key.c.declined.is_not(None), USER_KEY_DECLINED),
                    (
                        sql.func.coalesce(
                            key.c.last_used, sql.cast(key.c.approved, Date)
                        )
                        < sql.func.current_date() - const.USER_KEY_LIFETIME_DAYS,
                        USER_KEY_EXPIRED,
                    ),
                    (key.c.approved.is_not(None), USER_KEY_APPROVED),
                    (
                        key.c.link_expires <= sql.func.clock_timestamp(),
                        USER_KEY_EXPIRED,
                    ),
                    else_=USER_KEY_PENDING,
                ),
            ).where(key.c.apikey == apikey),
        )
        .order_by("priority")
        .limit(1)
    )
    row = conn.execute(query).fetchone()
    if row is None:
        return None
    return UserKey(row.account_id, row.application_id, row.state)


# Crockford base32: no I, L, O or U, so a code survives being read aloud.
LINK_CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
LINK_CODE_LENGTH = 8


def generate_link_code() -> str:
    return "".join(secrets.choice(LINK_CODE_ALPHABET) for _ in range(LINK_CODE_LENGTH))


def format_link_code(code: str) -> str:
    return code[:4] + "-" + code[4:]


def normalize_link_code(code: str) -> str:
    code = re.sub(r"[\s-]", "", code).upper()
    return code.replace("O", "0").replace("I", "1").replace("L", "1")


class LinkRequest(NamedTuple):
    id: int
    apikey: str
    link_code: str
    link_expires: datetime.datetime


def create_user_key_link_request(
    conn: AppDB,
    application_id: int,
    device: str | None,
    return_url: str | None = None,
) -> LinkRequest:
    key = schema.account_application_key
    for _ in range(5):
        apikey = generate_api_key()
        values = sql.select(
            sql.literal(apikey),
            sql.literal(application_id),
            sql.literal(device, String),
            sql.literal(return_url, String),
            sql.literal(generate_link_code()),
            sql.func.now() + const.USER_KEY_LINK_TTL,
        ).where(
            ~sql.exists().where(schema.account.c.apikey == apikey),
        )
        stmt = (
            insert(key)
            .from_select(
                [
                    "apikey",
                    "application_id",
                    "device",
                    "return_url",
                    "link_code",
                    "link_expires",
                ],
                values,
            )
            .on_conflict_do_nothing()
            .returning(key.c.id, key.c.apikey, key.c.link_code, key.c.link_expires)
        )
        row = conn.execute(stmt).fetchone()
        if row is not None:
            return LinkRequest(row.id, row.apikey, row.link_code, row.link_expires)
    raise Exception("Failed to generate a unique user key")


def count_pending_link_requests(conn: AppDB, application_id: int, limit: int) -> int:
    """Live link codes for the application, counting no further than limit."""
    key = schema.account_application_key
    pending = (
        sql.select(sql.literal(1))
        .where(key.c.application_id == application_id)
        .where(key.c.link_code.is_not(None))
        .where(key.c.link_expires > sql.func.clock_timestamp())
        .limit(limit)
        .subquery()
    )
    return conn.execute(sql.select(sql.func.count()).select_from(pending)).scalar_one()


class UserKeyStatus(NamedTuple):
    state: str
    # When the link code stops working, for a pending key only.
    expires: datetime.datetime | None


def get_user_key_status(conn: AppDB, apikey: str) -> UserKeyStatus | None:
    key = lookup_user_api_key(conn, apikey)
    if key is None:
        return None
    expires = None
    if key.state == USER_KEY_PENDING:
        table = schema.account_application_key
        query = sql.select(table.c.link_expires).where(table.c.apikey == apikey)
        expires = conn.execute(query).scalar_one()
    return UserKeyStatus(key.state, expires)


def _update_pending_link(code: str) -> Any:
    key = schema.account_application_key
    return (
        key.update()
        .where(key.c.link_code == normalize_link_code(code))
        .where(key.c.account_id.is_(None))
        .where(key.c.declined.is_(None))
        .where(key.c.link_expires > sql.func.clock_timestamp())
        .returning(key.c.apikey)
    )


def approve_user_key_link_request(
    conn: AppDB, code: str, account_id: int
) -> str | None:
    """Bind the pending key to the account. Returns the key, or None if the code
    does not name a pending request."""
    stmt = _update_pending_link(code).values(
        account_id=account_id, approved=sql.func.now(), link_code=None
    )
    return conn.execute(stmt).scalar()


def decline_user_key_link_request(conn: AppDB, code: str) -> str | None:
    stmt = _update_pending_link(code).values(declined=sql.func.now(), link_code=None)
    return conn.execute(stmt).scalar()


def revoke_user_application_key(conn: AppDB, id: int, account_id: int) -> str | None:
    """Returns the revoked key, or None if the account has no such live key."""
    key = schema.account_application_key
    stmt = (
        key.update()
        .where(key.c.id == id)
        .where(key.c.account_id == account_id)
        .where(key.c.revoked.is_(None))
        .values(revoked=sql.func.now())
        .returning(key.c.apikey)
    )
    return conn.execute(stmt).scalar()


# User keys are cached in Redis, shared by every API process. The API fills
# the cache only where it is empty (SET NX); whatever changes a key's state
# overwrites the entry after committing, so a process holding a stale read
# from a replica cannot undo the change.
USER_KEY_CACHE_PREFIX = "userkey:"
USER_KEY_CACHE_TTL = 600
# Short, because a key just issued may not have reached the replica the API
# reads, and nothing overwrites an entry saying it does not exist.
UNKNOWN_USER_KEY_CACHE_TTL = 5


def read_cached_user_key(redis: Redis, apikey: str) -> tuple[bool, UserKey | None]:
    """(found, key). A found entry can be None, meaning the key is unknown."""
    value = redis.get(USER_KEY_CACHE_PREFIX + apikey)
    if value is None:
        return False, None
    try:
        data = json.loads(value)
        return True, None if data is None else UserKey(*data)
    except (ValueError, TypeError):
        # Written by a version with a different UserKey, say.
        return False, None


def cache_user_key(
    redis: Redis, apikey: str, key: UserKey | None, replace: bool = False
) -> None:
    redis.set(
        USER_KEY_CACHE_PREFIX + apikey,
        json.dumps(None if key is None else list(key)),
        ex=UNKNOWN_USER_KEY_CACHE_TTL if key is None else USER_KEY_CACHE_TTL,
        nx=not replace,
    )


def refresh_cached_user_key(redis: Redis, conn: AppDB, apikey: str) -> None:
    """Overwrite the cached state of a key that has just changed. Call after
    committing, with a connection to the primary.

    A failure is logged rather than raised: the change is already committed,
    and the stale entry expires within USER_KEY_CACHE_TTL.
    """
    try:
        cache_user_key(redis, apikey, lookup_user_api_key(conn, apikey), replace=True)
    except Exception:
        logger.error("Failed to update cached user key", exc_info=True)


def get_pending_link_request(conn: AppDB, code: str) -> dict[str, Any] | None:
    """What the consent screen shows about a link request still waiting for a
    decision, or None if the code does not name one."""
    key = schema.account_application_key
    app = schema.application
    query = (
        sql.select(
            key.c.id,
            key.c.device,
            key.c.created,
            key.c.return_url,
            key.c.link_expires,
            app.c.id.label("application_id"),
            app.c.name.label("application_name"),
            app.c.created.label("application_created"),
            app.c.website.label("application_website"),
        )
        .select_from(key.join(app, app.c.id == key.c.application_id))
        .where(key.c.link_code == normalize_link_code(code))
        .where(key.c.account_id.is_(None))
        .where(key.c.declined.is_(None))
        .where(key.c.link_expires > sql.func.clock_timestamp())
    )
    row = conn.execute(query).fetchone()
    return dict(row._mapping) if row else None


def list_user_application_keys(conn: AppDB, account_id: int) -> list[dict[str, Any]]:
    """Keys the account has approved, live ones first."""
    key = schema.account_application_key
    app = schema.application
    query = (
        sql.select(
            key.c.id,
            key.c.device,
            key.c.approved,
            key.c.revoked,
            key.c.last_used,
            app.c.id.label("application_id"),
            app.c.name.label("application_name"),
        )
        .select_from(key.join(app, app.c.id == key.c.application_id))
        .where(key.c.account_id == account_id)
        .order_by(key.c.revoked.is_not(None), key.c.approved.desc())
    )
    return [dict(row._mapping) for row in conn.execute(query)]


def revoke_all_user_application_keys(conn: AppDB, account_id: int) -> list[str]:
    """Returns the keys revoked."""
    key = schema.account_application_key
    stmt = (
        key.update()
        .where(key.c.account_id == account_id)
        .where(key.c.revoked.is_(None))
        .values(revoked=sql.func.now())
        .returning(key.c.apikey)
    )
    return list(conn.execute(stmt).scalars())


USER_KEY_USED_PREFIX = "userkeyused:"
# The dates a process has already recorded each key for, so a busy key costs
# one redis write per process per day rather than one per request.
_recorded_user_key_use: cachetools.Cache = cachetools.TTLCache(maxsize=10000, ttl=3600)


def record_user_key_use(redis: Redis, apikey: str, today: datetime.date) -> None:
    """Note that a linked key was used today, for flush_user_key_use to write
    to the database. Never fails the request."""
    if _recorded_user_key_use.get(apikey) == today:
        return
    key = USER_KEY_USED_PREFIX + today.isoformat()
    try:
        pipe = redis.pipeline()
        pipe.sadd(key, apikey)
        pipe.expire(key, 7 * 24 * 3600)
        pipe.execute()
    except Exception:
        logger.warning("Failed to record user key use", exc_info=True)
        return
    _recorded_user_key_use[apikey] = today


def mark_user_keys_used(conn: AppDB, apikeys: list[str], date: datetime.date) -> None:
    key = schema.account_application_key
    stmt = (
        key.update()
        .where(key.c.apikey.in_(apikeys))
        .where(sql.or_(key.c.last_used.is_(None), key.c.last_used < date))
        .values(last_used=date)
    )
    conn.execute(stmt)


def delete_abandoned_link_requests(conn: AppDB) -> int:
    key = schema.account_application_key
    stmt = (
        key.delete()
        .where(key.c.account_id.is_(None))
        .where(
            key.c.link_expires < sql.func.now() - const.ABANDONED_LINK_REQUEST_RETENTION
        )
    )
    return conn.execute(stmt).rowcount
