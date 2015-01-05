# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import urllib
import logging
import datetime
from sqlalchemy import sql
from acoustid import tables as schema

logger = logging.getLogger(__name__)


def find_current_stats(conn):
    query = schema.stats.select(schema.stats.c.date == sql.select([sql.func.max(schema.stats.c.date)]))
    stats = {}
    for row in conn.execute(query):
        stats[row['name']] = row['value']
    return stats


def find_daily_stats(conn, names):
    query = """
        SELECT
            date, name,
            value - lag(value, 1, 0) over(PARTITION BY name ORDER BY date) AS value
        FROM stats
        WHERE date > now() - INTERVAL '31 day' AND name IN (""" + ",".join(["%s" for i in names]) +  """)
        ORDER BY name, date
    """
    stats = {}
    for name in names:
        stats[name] = []
    seen = set()
    for row in conn.execute(query, tuple(names)).fetchall():
        name = row['name']
        if name not in seen:
            seen.add(name)
            continue
        stats[row['name']].append({'date': row['date'], 'value': row['value']})
    return stats


def find_lookup_stats(conn):
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
    parts = [
        datetime.datetime.now().strftime('%Y-%m-%d:%H'),
        str(application_id),
        str(type),
    ]
    return ':'.join(parts)


def unpack_lookup_stats_key(key):
    parts = key.split(':')
    if len(parts) >= 4:
        date, hour, application_id, type = parts[:4]
        return date, hour, application_id, type
    raise ValueError('invalid lookup stats key')


def update_lookup_counter(redis, application_id, hit):
    if redis is None:
        return
    type = 'hit' if hit else 'miss'
    key = pack_lookup_stats_key(application_id, type)
    try:
        redis.hincrby('lookups', key, 1)
    except Exception:
        logger.exception("Can't update lookup stats for %s" % key)


def pack_user_agent_stats_key(application_id, user_agent, ip):
    parts = [
        datetime.datetime.now().strftime('%Y-%m-%d'),
        str(application_id),
        urllib.quote(str(user_agent)),
        urllib.quote(str(ip)),
    ]
    return ':'.join(parts)


def unpack_user_agent_stats_key(key):
    parts = key.split(':')
    if len(parts) >= 4:
        date, application_id, user_agent, ip = parts[:5]
        return date, application_id, urllib.unquote(user_agent), urllib.unquote(ip)
    raise ValueError('invalid lookup user agent stats key')


def update_user_agent_counter(redis, application_id, user_agent, ip):
    if redis is None:
        return
    key = pack_user_agent_stats_key(application_id, user_agent, ip)
    try:
        redis.hincrby('ua', key, 1)
    except Exception:
        logger.exception("Can't update user agent stats for %s" % key)


def update_lookup_avg_time(redis, seconds):
    if redis is None:
        return
    key = datetime.datetime.now().strftime('%Y-%m-%d:%H:%M')
    try:
        tx = redis.pipeline()
        tx.hincrby('lookups.time.ms', key, int(round(1000 * seconds))) # XXX use hincrbyfloat and seconds
        tx.hincrby('lookups.time.count', key, 1)
        tx.execute()
    except Exception:
        logger.exception("Can't update lookup avg time for %s" % key)


def update_lookup_stats(db, application_id, date, hour, type, count):
    if type == 'hit':
        column = schema.stats_lookups.c.count_hits
    else:
        column = schema.stats_lookups.c.count_nohits
    with db.begin():
        db.execute("LOCK TABLE stats_lookups IN EXCLUSIVE MODE")
        query = sql.select([schema.stats_lookups.c.id]).\
            where(schema.stats_lookups.c.application_id == application_id).\
            where(schema.stats_lookups.c.date == date).\
            where(schema.stats_lookups.c.hour == hour)
        stats_id = db.execute(query).scalar()
        if stats_id:
            stmt = schema.stats_lookups.update().\
                where(schema.stats_lookups.c.id == stats_id).\
                values({column: column + count})
        else:
            stmt = schema.stats_lookups.insert().\
                values({
                    schema.stats_lookups.c.application_id: application_id,
                    schema.stats_lookups.c.date: date,
                    schema.stats_lookups.c.hour: hour,
                    column: count,
                })
        db.execute(stmt)


def update_user_agent_stats(db, application_id, date, hour, user_agent, ip, count):
    with db.begin():
        db.execute("LOCK TABLE stats_user_agents IN EXCLUSIVE MODE")
        query = sql.select([schema.stats_user_agents.c.id]).\
            where(schema.stats_user_agents.c.application_id == application_id).\
            where(schema.stats_user_agents.c.date == date).\
            where(schema.stats_user_agents.c.user_agent == user_agent).\
            where(schema.stats_user_agents.c.ip == ip)
        stats_id = db.execute(query).scalar()
        if stats_id:
            stmt = schema.stats_user_agents.update().\
                where(schema.stats_user_agents.c.id == stats_id).\
                values({schema.stats_user_agents.c.count: schema.stats_user_agents.c.count + count})
        else:
            stmt = schema.stats_user_agents.insert().\
                values({
                    schema.stats_user_agents.c.application_id: application_id,
                    schema.stats_user_agents.c.date: date,
                    schema.stats_user_agents.c.user_agent: user_agent,
                    schema.stats_user_agents.c.ip: ip,
                    schema.stats_user_agents.c.count: count,
                })
        db.execute(stmt)


def find_application_lookup_stats(conn, application_id):
    query = """
        SELECT
            date,
            sum(count_hits) AS count_hits,
            sum(count_nohits) AS count_nohits,
            sum(count_hits) + sum(count_nohits) AS count
        FROM stats_lookups
        WHERE
            application_id = %s AND
            date > now() - INTERVAL '30 day' AND date < date(now())
        GROUP BY date
        ORDER BY date
    """
    stats = []
    for row in conn.execute(query, (application_id,)):
        stats.append(dict(row))
    return stats


def find_top_contributors(conn):
    src = schema.stats_top_accounts.join(schema.account)
    query = sql.select([
        schema.account.c.name,
        schema.account.c.mbuser,
        schema.stats_top_accounts.c.count
    ], from_obj=src)
    query = query.order_by(schema.stats_top_accounts.c.count.desc(),
                           schema.account.c.name,
                           schema.account.c.id)
    results = []
    for row in conn.execute(query):
        results.append({
            'name': row[schema.account.c.name],
            'mbuser': row[schema.account.c.mbuser],
            'count': row[schema.stats_top_accounts.c.count],
        })
    return results


def find_all_contributors(conn):
    query = sql.select([
        schema.account.c.name,
        schema.account.c.mbuser,
        schema.account.c.submission_count,
    ])
    query = query.where(schema.account.c.submission_count > 0)
    query = query.where(schema.account.c.anonymous == False)
    query = query.order_by(schema.account.c.submission_count.desc(),
                           schema.account.c.name,
                           schema.account.c.id)
    results = []
    for row in conn.execute(query):
        results.append({
            'name': row[schema.account.c.name],
            'mbuser': row[schema.account.c.mbuser],
            'count': row[schema.account.c.submission_count],
        })
    return results



