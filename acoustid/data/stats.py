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

