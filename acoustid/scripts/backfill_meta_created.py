#!/usr/bin/env python

# Copyright (C) 2019 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables

logger = logging.getLogger(__name__)


def run_backfill_meta_created(script, opts, args):
    if script.config.cluster.role != 'master':
        logger.info('Not running backfill_meta_created in slave mode')
        return

    query = """
        WITH meta_created AS (
          SELECT meta_id, min(created) AS created
          FROM track_meta
          WHERE meta_id IN (SELECT id FROM meta WHERE created IS NULL LIMIT 10000)
          GROUP BY meta_id
        )
        UPDATE meta
        SET created = meta_created.created
        FROM meta_created
        WHERE meta.id = meta_created.meta_id
    """

    for i in range(100):
        with script.context() as ctx:
            fingerprint_db = ctx.db.get_fingerprint_db()
            fingerprint_db.execute(query)
            ctx.db.session.commit()
