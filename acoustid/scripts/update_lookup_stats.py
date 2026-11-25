# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
import logging
import time
from collections import Counter, defaultdict

from sqlalchemy.exc import IntegrityError

from acoustid.data.account import mark_user_key_used
from acoustid.data.stats import (
    NUM_PARTITIONS,
    LookupStatsKey,
    unpack_lookup_stats_key,
    update_lookup_stats,
    update_user_lookup_stats,
)
from acoustid.script import Script, ScriptContext
from acoustid.tasks import enqueue_task

logger = logging.getLogger(__name__)


# SQLSTATE for foreign_key_violation. A counter keyed on an application that
# does not exist can never be applied, however often it is retried.
FOREIGN_KEY_VIOLATION = "23503"


def _is_unknown_application(error: IntegrityError) -> bool:
    return getattr(error.orig, "pgcode", None) == FOREIGN_KEY_VIOLATION


def run_update_all_lookup_stats(script: Script) -> None:
    delay = 60.0 / NUM_PARTITIONS
    with script.context() as ctx:
        for partition in range(-1, NUM_PARTITIONS):
            enqueue_task(ctx, "update_lookup_stats", {"partition": partition})
            time.sleep(delay)


def run_update_lookup_stats(script: Script, partition: int):
    if partition == -1:
        root_key = "lookups"
    else:
        root_key = f"lookups:{partition:02x}"
    logger.debug("Updating lookup stats (key %s)", root_key)
    with script.context() as ctx:
        redis = ctx.redis
        groups: dict[int, list[tuple[bytes, int, LookupStatsKey]]] = defaultdict(list)
        for raw_key, raw_count in redis.hgetall(root_key).items():
            count = int(raw_count)
            if not count:
                # the only way this could be 0 is if we already processed it and
                # nothing touched it since then, so it's safe to delete
                redis.hdel(root_key, raw_key)
                continue
            try:
                key = unpack_lookup_stats_key(raw_key)
            except ValueError:
                logger.warning("Discarding invalid lookup stats key %r", raw_key)
                redis.hdel(root_key, raw_key)
                continue
            groups[key.application_id].append((raw_key, count, key))

        # One application at a time, each in its own transaction, so a
        # counter that can never be written only takes its own application's
        # counters with it.
        for application_id, group in groups.items():
            try:
                write_lookup_stats(ctx, application_id, group)
                ctx.db.session.commit()
            except IntegrityError as error:
                if not _is_unknown_application(error):
                    raise
                # Left in place it fails the same way on every run, and
                # takes every counter behind it in this partition with it.
                ctx.db.session.rollback()
                logger.warning(
                    "Discarding lookup stats for unknown application %s",
                    application_id,
                )
                for raw_key, _, _ in group:
                    redis.hdel(root_key, raw_key)
                continue
            for raw_key, count, _ in group:
                redis.hincrby(root_key, raw_key, -count)


def write_lookup_stats(
    ctx: ScriptContext,
    application_id: int,
    group: list[tuple[bytes, int, LookupStatsKey]],
) -> None:
    """Sum one application's counters and write them: per hour to
    stats_lookups, per account and day to stats_user_lookups, and the day a
    linked key was used to its last_used.

    Summed first because the counters are per user: written one by one, a
    popular application's stats_lookups row would be updated thousands of
    times a minute.
    """
    db = ctx.db.get_app_db()
    app_counts: Counter[tuple[str, str, str]] = Counter()
    user_counts: Counter[tuple[str, int, str]] = Counter()
    key_dates: dict[int, str] = {}
    for _, count, key in group:
        app_counts[key.date, key.hour, key.type] += count
        if key.account_id is not None:
            user_counts[key.date, key.account_id, key.type] += count
        if key.key_id is not None:
            key_dates[key.key_id] = max(key.date, key_dates.get(key.key_id, ""))

    # Sorted, so flushes of different partitions running at the same time
    # lock rows in the same order and cannot deadlock.
    for (date, hour, type), count in sorted(app_counts.items()):
        update_lookup_stats(db, application_id, date, hour, type, count)
    for date, account_id in sorted({(d, a) for d, a, _ in user_counts}):
        update_user_lookup_stats(
            db,
            date,
            account_id,
            application_id,
            hits=user_counts[date, account_id, "hit"],
            nohits=user_counts[date, account_id, "miss"],
        )
    for key_id, date in sorted(key_dates.items()):
        mark_user_key_used(db, key_id, datetime.date.fromisoformat(date))
