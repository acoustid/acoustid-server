#!/usr/bin/env python

# Copyright (C) 2019 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging

logger = logging.getLogger(__name__)


def run_backfill_meta_created(script, opts, args):
    if script.config.cluster.role != 'master':
        logger.info('Not running backfill_meta_created in slave mode')
        return

    last_meta_id_query = """
        SELECT max(id) FROM meta WHERE created IS NULL
    """

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
        WHERE meta.id = meta_created.meta_id AND meta.created IS NULL AND meta.id > %(first_meta_id)s AND meta.id <= %(last_meta_id)s
    """

    with script.context() as ctx:
        fingerprint_db = ctx.db.get_fingerprint_db()
        last_meta_id = fingerprint_db.execute(last_meta_id_query).scalar()
        if last_meta_id is None:
            return
        first_meta_id = last_meta_id - 10000
        result = fingerprint_db.execute(update_query, {'first_meta_id': first_meta_id, 'last_meta_id': last_meta_id})
        logger.info('Added create date to %s meta entries', result.rowcount)
        if result.rowcount == 0:
            return
        ctx.db.session.commit()
