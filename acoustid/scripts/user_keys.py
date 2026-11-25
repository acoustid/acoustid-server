# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
import time

from sqlalchemy.exc import IntegrityError

from acoustid.data.account import delete_abandoned_link_requests, mark_user_key_used
from acoustid.data.stats import (
    NUM_PARTITIONS,
    delete_old_user_lookup_stats,
    unpack_user_stats_key,
    update_user_lookup_stats,
    user_stats_root_key,
)
from acoustid.script import Script
from acoustid.tasks import enqueue_task

logger = logging.getLogger(__name__)


def run_update_all_user_stats(script: Script) -> None:
    delay = 60.0 / NUM_PARTITIONS
    with script.context() as ctx:
        for partition in range(NUM_PARTITIONS):
            enqueue_task(ctx, "update_user_stats", {"partition": partition})
            time.sleep(delay)


def run_update_user_stats(script: Script, partition: int) -> None:
    """Write one partition of the per-user counters to the database: lookups to
    stats_user_lookups, and any use of a linked key to its last_used.

    Like the lookup counters, each counter is decremented by what was written
    only after the write is committed, so a failure leaves it for the next run.
    """
    root_key = user_stats_root_key(partition)
    with script.context() as ctx:
        redis = ctx.redis
        for raw_key, raw_count in redis.hgetall(root_key).items():
            count = int(raw_count)
            if not count:
                redis.hdel(root_key, raw_key)
                continue
            try:
                key = unpack_user_stats_key(raw_key)
            except ValueError:
                logger.warning("Discarding invalid user stats key %r", raw_key)
                redis.hdel(root_key, raw_key)
                continue
            db = ctx.db.get_app_db()
            try:
                if key.type != "submit":
                    update_user_lookup_stats(
                        db,
                        key.date,
                        key.account_id,
                        key.application_id,
                        key.type,
                        count,
                    )
                if key.key_id is not None:
                    mark_user_key_used(db, key.key_id, key.date)
                ctx.db.session.commit()
            except IntegrityError:
                # An account or application deleted since; this can never be
                # written, and would block the counters behind it.
                ctx.db.session.rollback()
                logger.warning("Discarding user stats for %r", raw_key)
                redis.hdel(root_key, raw_key)
                continue
            redis.hincrby(root_key, raw_key, -count)


def run_cleanup_user_keys(script: Script) -> None:
    with script.context() as ctx:
        db = ctx.db.get_app_db()
        requests = delete_abandoned_link_requests(db)
        stats = delete_old_user_lookup_stats(db)
        ctx.db.session.commit()
        logger.info(
            "Deleted %d abandoned link requests and %d old user stats rows",
            requests,
            stats,
        )
