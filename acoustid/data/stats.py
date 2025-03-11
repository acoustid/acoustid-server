# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
import logging
import urllib.parse
from typing import Any, Iterable, Optional, Tuple, Union

from sqlalchemy import sql
from sqlalchemy.dialects.postgresql import insert

from acoustid import tables as schema
from acoustid.db import AppDB

logger = logging.getLogger(__name__)

NUM_PARTITIONS = 256


def find_current_stats(conn: AppDB) -> dict[str, int]:
    subquery = sql.select(sql.func.max(schema.stats.c.date)).scalar_subquery()
    query = sql.select(schema.stats).where(schema.stats.c.date == subquery)
    stats = {}
    for row in conn.execute(query):
        stats[row.name] = row.value
    return stats


def find_daily_stats(conn: AppDB, names: list[str]) -> list[dict[str, Any]]:
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
        stats.append(dict(row))
    return stats


def pack_lookup_stats_key(application_id: int, type: str) -> str:
    parts = [
        datetime.datetime.now().strftime("%Y-%m-%d:%H"),
        str(application_id),
        str(type),
    ]
    return ":".join(parts)


def unpack_lookup_stats_key(key: Union[str, bytes]) -> Tuple[str, str, int, str]:
    if isinstance(key, bytes):
        key = key.decode("utf8")
    parts = key.split(":")
    if len(parts) >= 4:
        date, hour, application_id, type = parts[:4]
        return date, hour, int(application_id), type
    raise ValueError("invalid lookup stats key")


def update_lookup_counter(redis, application_id: int, hit: bool) -> None:
    if redis is None:
        return
    type = "hit" if hit else "miss"
    key = pack_lookup_stats_key(application_id, type)
    root_key_index = hash(key) % NUM_PARTITIONS
    root_key = f"lookups:{root_key_index:02x}"
    try:
        redis.hincrby(root_key, key, 1)
    except Exception:
        logger.exception("Can't update lookup stats for %s" % key)


def pack_user_agent_stats_key(application_id: int, user_agent: str, ip: str) -> str:
    parts = [
        datetime.datetime.now().strftime("%Y-%m-%d"),
        str(application_id),
        urllib.parse.quote(str(user_agent)),
        urllib.parse.quote(str(ip)),
    ]
    return ":".join(parts)


def unpack_user_agent_stats_key(key: Union[str, bytes]) -> Tuple[str, int, str, str]:
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
        logger.exception("Can't update user agent stats for %s" % key)


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
    from_date: Optional[datetime.date] = None,
    to_date: Optional[datetime.date] = None,
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

    return [dict(row) for row in conn.execute(query)]


def find_application_lookup_stats(
    conn: AppDB, application_id: int
) -> list[dict[str, Any]]:
    return find_application_lookup_stats_multi(conn, (application_id,))
