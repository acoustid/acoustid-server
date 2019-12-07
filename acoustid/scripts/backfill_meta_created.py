#!/usr/bin/env python

# Copyright (C) 2019 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging

logger = logging.getLogger(__name__)


def run_backfill_meta_created(script, opts, args):
    if script.config.cluster.role != 'master':
        logger.info('Not running backfill_meta_created in slave mode')
        return

    update_query = """
        WITH meta_created AS (
          SELECT meta_id, min(created) AS created
          FROM track_meta
          WHERE meta_id > %(first_meta_id)s AND meta_id <= %(last_meta_id)s
          GROUP BY meta_id
        )
        UPDATE meta
        SET created = meta_created.created
        FROM meta_created
        WHERE meta.id = meta_created.meta_id AND meta.created IS NULL AND meta.id >= %(first_meta_id)s AND meta.id < %(last_meta_id)s
    """

    for i in range(100):
        with script.context() as ctx:
            first_meta_id = int(ctx.redis.get('backfill_meta_created_first_id') or 0)
            last_meta_id = first_meta_id + 10000
            fingerprint_db = ctx.db.get_fingerprint_db()
            result = fingerprint_db.execute(update_query, {'first_meta_id': first_meta_id, 'last_meta_id': last_meta_id})
            logger.info('Added create date to %s meta entries between (%d and %d)', result.rowcount, first_meta_id, last_meta_id)
            ctx.db.session.commit()
            ctx.redis.set('backfill_meta_created_first_id', str(last_meta_id))
