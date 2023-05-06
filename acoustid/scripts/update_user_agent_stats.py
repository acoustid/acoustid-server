# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import time
import logging

from acoustid.script import Script
from acoustid.tasks import enqueue_task
from acoustid.utils import call_internal_api
from acoustid.data.stats import update_user_agent_stats, unpack_user_agent_stats_key, NUM_PARTITIONS

logger = logging.getLogger(__name__)


def run_update_all_user_agent_stats(script: Script) -> None:
    delay = 60.0 / NUM_PARTITIONS
    with script.context() as ctx:
        for partition in range(-1, NUM_PARTITIONS):
            enqueue_task(ctx, 'update_user_agent_stats', {'partition': partition})
            time.sleep(delay)


def run_update_user_agent_stats(script: Script, partition: int):
    if partition == -1:
        root_key = 'ua'
    else:
        root_key = f'ua:{partition:02x}'
    logger.info('Updating user agent stats (key %s)', root_key)
    db = script.db_engines['app'].connect()
    redis = script.get_redis()
    for key, count in redis.hgetall(root_key).items():
        count = int(count)
        date, application_id, user_agent, ip = unpack_user_agent_stats_key(key)
        if not count:
            # the only way this could be 0 is if we already processed it and
            # nothing touched it since then, so it's safe to delete
            redis.hdel(root_key, key)
        else:
            if script.config.cluster.role == 'master':
                update_user_agent_stats(db, application_id, date, user_agent, ip, count)
            else:
                call_internal_api(script.config, 'update_user_agent_stats',
                    application_id=application_id, date=date,
                    user_agent=user_agent, ip=ip, count=count)
            redis.hincrby(root_key, key, -count)
