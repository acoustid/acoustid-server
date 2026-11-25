# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
import logging
from itertools import islice

from acoustid.data.account import (
    USER_KEY_USED_PREFIX,
    delete_abandoned_link_requests,
    mark_user_keys_used,
)
from acoustid.script import Script

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


def run_flush_user_key_use(script: Script) -> None:
    """Write the use the API recorded in redis to account_application_key.last_used.

    Each batch is removed from redis only after it is committed, so a failure
    leaves it for the next run.
    """
    with script.context() as ctx:
        for name in ctx.redis.scan_iter(USER_KEY_USED_PREFIX + "*"):
            if isinstance(name, bytes):
                name = name.decode()
            date = datetime.date.fromisoformat(name.removeprefix(USER_KEY_USED_PREFIX))
            members = ctx.redis.sscan_iter(name, count=BATCH_SIZE)
            while batch := list(islice(members, BATCH_SIZE)):
                apikeys = [m.decode() if isinstance(m, bytes) else m for m in batch]
                mark_user_keys_used(ctx.db.get_app_db(), apikeys, date)
                ctx.db.session.commit()
                ctx.redis.srem(name, *batch)
                logger.info("Marked %d user keys as used on %s", len(apikeys), date)


def run_cleanup_link_requests(script: Script) -> None:
    with script.context() as ctx:
        count = delete_abandoned_link_requests(ctx.db.get_app_db())
        ctx.db.session.commit()
        if count:
            logger.info("Deleted %d abandoned link requests", count)
