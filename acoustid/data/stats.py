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

