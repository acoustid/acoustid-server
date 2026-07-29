# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
import time

from sqlalchemy.exc import IntegrityError

from acoustid.data.stats import (
    NUM_PARTITIONS,
    unpack_user_agent_stats_key,
    update_user_agent_stats,
)
from acoustid.script import Script
from acoustid.tasks import enqueue_task
from acoustid.utils import call_internal_api

logger = logging.getLogger(__name__)


# SQLSTATE for foreign_key_violation. A counter keyed on an application that
# does not exist can never be applied, however often it is retried.
FOREIGN_KEY_VIOLATION = "23503"


def _is_unknown_application(error: IntegrityError) -> bool:
    return getattr(error.orig, "pgcode", None) == FOREIGN_KEY_VIOLATION


def run_update_all_user_agent_stats(script: Script) -> None:
    delay = 60.0 / NUM_PARTITIONS
    with script.context() as ctx:
        for partition in range(-1, NUM_PARTITIONS):
            enqueue_task(ctx, "update_user_agent_stats", {"partition": partition})
            time.sleep(delay)


def run_update_user_agent_stats(script: Script, partition: int) -> None:
    if partition == -1:
        root_key = "ua"
    else:
        root_key = f"ua:{partition:02x}"
    logger.debug("Updating user agent stats (key %s)", root_key)
    with script.context() as ctx:
        redis = ctx.redis
        for key, count in redis.hgetall(root_key).items():
            db = ctx.db.get_app_db()
            count = int(count)
            date, application_id, user_agent, ip = unpack_user_agent_stats_key(key)
            if not count:
                # the only way this could be 0 is if we already processed it and
                # nothing touched it since then, so it's safe to delete
                redis.hdel(root_key, key)
            else:
                try:
                    if script.config.cluster.role == "master":
                        update_user_agent_stats(
                            db, application_id, date, user_agent, ip, count
                        )
                    else:
                        call_internal_api(
                            script.config,
                            "update_user_agent_stats",
                            application_id=application_id,
                            date=date,
                            user_agent=user_agent,
                            ip=ip,
                            count=count,
                        )
                except IntegrityError as error:
                    if not _is_unknown_application(error):
                        raise
                    ctx.db.session.rollback()
                    logger.warning(
                        "Discarding user agent stats for unknown application %s (key %s)",
                        application_id,
                        key,
                    )
                    redis.hdel(root_key, key)
                    continue
                redis.hincrby(root_key, key, -count)
            ctx.db.session.commit()
