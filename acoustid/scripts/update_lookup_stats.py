# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import time
from acoustid.utils import call_internal_api
from acoustid.data.stats import update_lookup_stats


def run_update_lookup_stats(script, opts, args):
    db = script.db_engines['app'].connect()
    redis = script.get_redis()
    for i in range(-1, 256):
        if i == -1:
            root_key = 'lookups'
        else:
            root_key = f'lookups:{i:02x}'
        for key, count in redis.hgetall(root_key).items():
            count = int(count)
            date, hour, application_id, type = key.split(':')
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
                    time.sleep(0.5)
                redis.hincrby(root_key, key, -count)
