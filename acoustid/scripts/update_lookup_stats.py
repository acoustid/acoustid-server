# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging

from acoustid.utils import call_internal_api
from acoustid.data.stats import update_lookup_stats, unpack_lookup_stats_key

logger = logging.getLogger(__name__)


def run_update_lookup_stats(script, opts, args):
    logger.info('Updating lookup stats')
    db = script.db_engines['app'].connect()
    redis = script.get_redis()
    for i in range(-1, 256):
        if i == -1:
            root_key = 'lookups'
        else:
            root_key = f'lookups:{i:02x}'
        logger.info('Checking key %s', root_key)
        for key, count in redis.hgetall(root_key).items():
            count = int(count)
            date, hour, application_id, type = unpack_lookup_stats_key(key)
            if not count:
                # the only way this could be 0 is if we already processed it and
                # nothing touched it since then, so it's safe to delete
                redis.hdel(root_key, key)
            else:
                if script.config.cluster.role == 'master':
                    update_lookup_stats(db, application_id, date, hour, type, count)
                else:
                    call_internal_api(script.config, 'update_lookup_stats',
                        application_id=application_id, date=date, hour=hour,
                        type=type, count=count)
                redis.hincrby(root_key, key, -count)
