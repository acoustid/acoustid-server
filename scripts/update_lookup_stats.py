#!/usr/bin/env python

# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from acoustid.utils import call_internal_api
from acoustid.script import run_script
from acoustid.data.stats import update_lookup_stats


def main(script, opts, args):
    db = script.engine.connect()
    redis = script.redis
    for key, count in redis.hgetall('lookups').iteritems():
        count = int(count)
        date, hour, application_id, type = key.split(':')
        if not count:
            # the only way this could be 0 is if we already processed it and
            # nothing touched it since then, so it's safe to delete
            redis.hdel('lookups', key)
        else:
            if script.config.cluster.role == 'master':
                update_lookup_stats(db, application_id, date, hour, type, count)
            else:
                call_internal_api(script.config, 'update_lookup_stats',
                    application_id=application_id, date=date, hour=hour,
                    type=type, count=count)
            redis.hincrby('lookups', key, -count)


run_script(main)

