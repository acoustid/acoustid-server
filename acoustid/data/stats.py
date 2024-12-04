# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

import urllib.parse
from sqlalchemy import sql
from sqlalchemy.dialects.postgresql import insert

from acoustid import tables as schema
from acoustid.db import AppDB

logger = logging.getLogger(__name__)

NUM_PARTITIONS = 256


def find_current_stats(conn):
    # type: (AppDB) -> Dict[str, int]
    query = schema.stats.select(
        schema.stats.c.date == sql.select([sql.func.max(schema.stats.c.date)])
    )
    stats = {}
    for row in conn.execute(query):
        stats[row["name"]] = row["value"]
    return stats


def find_daily_stats(conn, names):
    # type: (AppDB, Iterable[str]) -> List[Dict[str, Any]]
    query = (
        """
        SELECT
            date, name,
            value - lag(value, 1, 0) over(PARTITION BY name ORDER BY date) AS value
        FROM stats
        WHERE date > now() - INTERVAL '31 day' AND name IN ("""
        + ",".join(["%s" for i in names])
        + """)
        ORDER BY date, name
    """
    )
    stats = []  # type: List[Dict[str, Any]]
    for date, name, value in conn.execute(query, tuple(names)).fetchall():
        if not stats or stats[-1]["date"] != date:
            stats.append({"date": date})
        stats[-1][name] = value
    return stats[1:]


def find_lookup_stats(conn):
    # type: (AppDB) -> List[Dict[str, Any]]
    query = """
        SELECT
            date,
            sum(count_hits) AS count_hits,
            sum(count_nohits) AS count_nohits,
            sum(count_hits) + sum(count_nohits) AS count
        FROM stats_lookups
        WHERE date > now() - INTERVAL '30 day' AND date < date(now())
        GROUP BY date
        ORDER BY date
    """
    stats = []
    for row in conn.execute(query):
        stats.append(dict(row))
    return stats


def pack_lookup_stats_key(application_id, type):
    # type: (int, str) -> str
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


def update_lookup_counter(redis, application_id, hit):
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


def pack_user_agent_stats_key(application_id, user_agent, ip):
    # type: (int, str, str) -> str
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


def update_user_agent_counter(redis, application_id, user_agent, ip):
    # type: (Any, int, str, str) -> None
    if redis is None:
        return
    key = pack_user_agent_stats_key(application_id, user_agent, ip)
    root_key_index = hash(key) % NUM_PARTITIONS
    root_key = f"ua:{root_key_index:02x}"
    try:
        redis.hincrby(root_key, key, 1)
    except Exception:
        logger.exception("Can't update user agent stats for %s" % key)


def update_lookup_stats(db, application_id, date, hour, type, count):
    # type: (AppDB, int, str, str, str, int) -> None
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


def update_user_agent_stats(db, application_id, date, user_agent, ip, count):
    # type: (AppDB, int, str, str, str, int) -> None

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
    conn, application_ids, from_date=None, to_date=None, days=30
):
    # type: (AppDB, Iterable[int], Optional[datetime.date], Optional[datetime.date], int) -> List[Dict[str, Any]]
    query = sql.select(
        [
            schema.stats_lookups.c.date,
            sql.func.sum(schema.stats_lookups.c.count_hits).label("count_hits"),
            sql.func.sum(schema.stats_lookups.c.count_nohits).label("count_nohits"),
            sql.func.sum(
                schema.stats_lookups.c.count_hits + schema.stats_lookups.c.count_nohits
            ).label("count"),
        ],
        from_obj=schema.stats_lookups,
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


def find_application_lookup_stats(conn, application_id):
    # type: (AppDB, int) -> List[Dict[str, Any]]
    return find_application_lookup_stats_multi(conn, (application_id,))
