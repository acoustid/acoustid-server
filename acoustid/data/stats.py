# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
import logging
import urllib.parse
from collections.abc import Iterable
from typing import Any, NamedTuple, Union

from redis import Redis
from sqlalchemy import Date, sql
from sqlalchemy.dialects.postgresql import insert

from acoustid import const
from acoustid import tables as schema
from acoustid.db import AppDB, DatabaseContext

logger = logging.getLogger(__name__)

NUM_PARTITIONS = 256


def find_current_stats(conn: AppDB) -> dict[str, int]:
    subquery = sql.select(sql.func.max(schema.stats.c.date)).scalar_subquery()
    query = sql.select(schema.stats).where(schema.stats.c.date == subquery)
    stats = {}
    for row in conn.execute(query):
        stats[row.name] = row.value
    return stats


def find_daily_stats(conn: AppDB, names: Iterable[str]) -> list[dict[str, Any]]:
    query = (
        sql.select(
            schema.stats.c.date,
            schema.stats.c.name,
            (
                schema.stats.c.value
                - sql.func.lag(schema.stats.c.value, 1, 0).over(
                    partition_by=schema.stats.c.name,
                    order_by=schema.stats.c.date,
                )
            ).label("value"),
        )
        .where(
            sql.and_(
                schema.stats.c.date > sql.func.now() - datetime.timedelta(days=31),
                schema.stats.c.name.in_(names),
            )
        )
        .order_by(schema.stats.c.date, schema.stats.c.name)
    )
    stats: list[dict[str, Any]] = []
    for date, name, value in conn.execute(query).fetchall():
        if not stats or stats[-1]["date"] != date:
            stats.append({"date": date})
        stats[-1][name] = value
    return stats[1:]


def find_lookup_stats(conn: AppDB) -> list[dict[str, Any]]:
    query = (
        sql.select(
            schema.stats_lookups.c.date,
            sql.func.sum(schema.stats_lookups.c.count_hits).label("count_hits"),
            sql.func.sum(schema.stats_lookups.c.count_nohits).label("count_nohits"),
            (
                sql.func.sum(schema.stats_lookups.c.count_hits)
                + sql.func.sum(schema.stats_lookups.c.count_nohits)
            ).label("count"),
        )
        .where(
            sql.and_(
                schema.stats_lookups.c.date
                > sql.func.now() - datetime.timedelta(days=30),
                schema.stats_lookups.c.date < sql.func.date(sql.func.now()),
            )
        )
        .group_by(schema.stats_lookups.c.date)
        .order_by(schema.stats_lookups.c.date)
    )
    stats = []
    for row in conn.execute(query):
        stats.append(dict(row._mapping))
    return stats


class LookupStatsKey(NamedTuple):
    date: str
    hour: str
    application_id: int
    type: str
    # Who looked up, when the request carried a user key. key_id is the
    # account_application_key row for a linked key, None for account.apikey.
    account_id: int | None = None
    key_id: int | None = None


def pack_lookup_stats_key(
    application_id: int,
    type: str,
    account_id: int | None = None,
    key_id: int | None = None,
) -> str:
    parts = [
        datetime.datetime.now().strftime("%Y-%m-%d:%H"),
        str(application_id),
        str(type),
    ]
    if account_id is not None:
        parts += [str(account_id), str(key_id or 0)]
    return ":".join(parts)


def unpack_lookup_stats_key(key: Union[str, bytes]) -> LookupStatsKey:
    if isinstance(key, bytes):
        key = key.decode("utf8")
    parts = key.split(":")
    if len(parts) == 4:
        date, hour, application_id, type = parts
        return LookupStatsKey(date, hour, int(application_id), type)
    if len(parts) == 6:
        date, hour, application_id, type, account_id, key_id = parts
        return LookupStatsKey(
            date, hour, int(application_id), type, int(account_id), int(key_id) or None
        )
    raise ValueError("invalid lookup stats key")


def update_lookup_counter(
    redis: Redis | None,
    application_id: int,
    hit: bool,
    account_id: int | None = None,
    key_id: int | None = None,
) -> None:
    if redis is None:
        return
    type = "hit" if hit else "miss"
    key = pack_lookup_stats_key(application_id, type, account_id, key_id)
    root_key_index = hash(key) % NUM_PARTITIONS
    root_key = f"lookups:{root_key_index:02x}"
    try:
        redis.hincrby(root_key, key, 1)
    except Exception:
        # Losing a counter increment does not affect the request that triggered
        # it, so this is not worth reporting per occurrence.
        logger.warning("Can't update lookup stats for %s" % key, exc_info=True)


def pack_user_agent_stats_key(application_id: int, user_agent: str, ip: str) -> str:
    parts = [
        datetime.datetime.now().strftime("%Y-%m-%d"),
        str(application_id),
        urllib.parse.quote(str(user_agent)),
        urllib.parse.quote(str(ip)),
    ]
    return ":".join(parts)


def unpack_user_agent_stats_key(key: Union[str, bytes]) -> tuple[str, int, str, str]:
    if isinstance(key, bytes):
        key = key.decode("utf8")
    parts = key.split(":")
    if len(parts) >= 4:
        date, application_id, user_agent, ip = parts[:5]
        return (
            date,
            int(application_id),
            urllib.parse.unquote(user_agent),
            urllib.parse.unquote(ip),
        )
    raise ValueError("invalid lookup user agent stats key")


def update_user_agent_counter(
    redis: Any, application_id: int, user_agent: str, ip: str
) -> None:
    if redis is None:
        return
    key = pack_user_agent_stats_key(application_id, user_agent, ip)
    root_key_index = hash(key) % NUM_PARTITIONS
    root_key = f"ua:{root_key_index:02x}"
    try:
        redis.hincrby(root_key, key, 1)
    except Exception:
        # As above -- a dropped counter, not a failed request.
        logger.warning("Can't update user agent stats for %s" % key, exc_info=True)


def update_lookup_stats(
    db: AppDB, application_id: int, date: str, hour: str, type: str, count: int
) -> None:
    if type == "hit":
        column = schema.stats_lookups.c.count_hits
    else:
        column = schema.stats_lookups.c.count_nohits

    insert_stmt = insert(schema.stats_lookups).values(
        {
            schema.stats_lookups.c.application_id: application_id,
            schema.stats_lookups.c.date: date,
            schema.stats_lookups.c.hour: hour,
            column: count,
        }
    )

    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=[
            schema.stats_lookups.c.application_id,
            schema.stats_lookups.c.date,
            schema.stats_lookups.c.hour,
        ],
        set_={
            column.name: column + count,
        },
    )

    db.execute(upsert_stmt)


def update_user_agent_stats(
    db: AppDB, application_id: int, date: str, user_agent: str, ip: str, count: int
) -> None:
    insert_stmt = insert(schema.stats_user_agents).values(
        {
            schema.stats_user_agents.c.application_id: application_id,
            schema.stats_user_agents.c.date: date,
            schema.stats_user_agents.c.user_agent: user_agent,
            schema.stats_user_agents.c.ip: ip,
            schema.stats_user_agents.c.count: count,
        }
    )

    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=[
            schema.stats_user_agents.c.application_id,
            schema.stats_user_agents.c.date,
            schema.stats_user_agents.c.user_agent,
            schema.stats_user_agents.c.ip,
        ],
        set_={
            schema.stats_user_agents.c.count.name: schema.stats_user_agents.c.count
            + count,
        },
    )

    db.execute(upsert_stmt)


def find_application_lookup_stats_multi(
    conn: AppDB,
    application_ids: Iterable[int],
    from_date: datetime.date | None = None,
    to_date: datetime.date | None = None,
    days: int = 30,
) -> list[dict[str, Any]]:
    query = sql.select(
        schema.stats_lookups.c.date,
        sql.func.sum(schema.stats_lookups.c.count_hits).label("count_hits"),
        sql.func.sum(schema.stats_lookups.c.count_nohits).label("count_nohits"),
        sql.func.sum(
            schema.stats_lookups.c.count_hits + schema.stats_lookups.c.count_nohits
        ).label("count"),
    ).group_by(schema.stats_lookups.c.date)

    if to_date is not None:
        query = query.where(schema.stats_lookups.c.date <= to_date)
    else:
        query = query.where(schema.stats_lookups.c.date < sql.func.date(sql.func.now()))

    if from_date is not None:
        query = query.where(schema.stats_lookups.c.date >= from_date)
    else:
        query = query.where(
            schema.stats_lookups.c.date
            > (sql.func.date(sql.func.now()) - datetime.timedelta(days=days))
        )

    if application_ids:
        query = query.where(schema.stats_lookups.c.application_id.in_(application_ids))

    query = query.order_by(schema.stats_lookups.c.date)
    return [dict(row._mapping) for row in conn.execute(query)]


def find_application_lookup_stats(
    conn: AppDB, application_id: int
) -> list[dict[str, Any]]:
    return find_application_lookup_stats_multi(conn, (application_id,))


def update_user_lookup_stats(
    db: AppDB,
    date: str,
    account_id: int,
    application_id: int,
    hits: int,
    nohits: int,
) -> None:
    """Add to an account's lookup counts for the day. A count for an account
    deleted since is dropped rather than failing the whole flush."""
    table = schema.stats_user_lookups
    values = sql.select(
        sql.literal(date).cast(Date),
        sql.literal(account_id),
        sql.literal(application_id),
        sql.literal(hits),
        sql.literal(nohits),
    ).where(sql.exists().where(schema.account.c.id == account_id))
    stmt = (
        insert(table)
        .from_select(
            ["date", "account_id", "application_id", "count_hits", "count_nohits"],
            values,
        )
        .on_conflict_do_update(
            index_elements=[table.c.date, table.c.account_id, table.c.application_id],
            set_={
                "count_hits": table.c.count_hits + hits,
                "count_nohits": table.c.count_nohits + nohits,
            },
        )
    )
    db.execute(stmt)


def delete_old_user_agent_stats(db: DatabaseContext) -> int:
    """Delete user agent stats older than the retention period, one day at
    a time, committing after each day so no single delete gets large."""
    table = schema.stats_user_agents
    cutoff = datetime.date.today() - const.USER_AGENT_STATS_RETENTION
    total = 0
    while True:
        # A commit releases the connection, so get it again for every day.
        conn = db.get_app_db()
        oldest = conn.execute(sql.select(sql.func.min(table.c.date))).scalar()
        if oldest is None or oldest >= cutoff:
            return total
        deleted = conn.execute(table.delete().where(table.c.date == oldest))
        total += deleted.rowcount
        db.session.commit()


def delete_old_user_lookup_stats(db: AppDB) -> int:
    table = schema.stats_user_lookups
    cutoff = datetime.date.today() - const.USER_LOOKUP_STATS_RETENTION
    return db.execute(table.delete().where(table.c.date < cutoff)).rowcount
