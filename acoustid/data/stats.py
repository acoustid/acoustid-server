# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
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
            value - first_value(value) over(PARTITION BY name
                                            ORDER BY date
                                            ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) AS value
        FROM stats
        WHERE date > now() - INTERVAL '30 day' AND name IN (""" + ",".join(["%s" for i in names]) +  """)
        ORDER BY name, date
    """
    stats = {}
    for name in names:
        stats[name] = []
    for row in conn.execute(query, tuple(names)):
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



