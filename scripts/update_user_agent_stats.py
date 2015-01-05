#!/usr/bin/env python

# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from contextlib import closing
from acoustid.utils import call_internal_api
from acoustid.script import run_script
from acoustid.data.stats import update_user_agent_stats, unpack_user_agent_stats_key


def main(script, opts, args):
    db = script.engine.connect()
    redis = script.redis
    for key, count in redis.hgetall('lookups.ua').iteritems():
        count = int(count)
        date, application_id, user_agent, ip = unpack_user_agent_stats_key(key)
        if not count:
            # the only way this could be 0 is if we already processed it and
            # nothing touched it since then, so it's safe to delete
            redis.hdel('lookups.ua', key)
        else:
            if script.config.cluster.role == 'master':
                update_user_agent_stats(db, application_id, date, user_agent, ip, count)
            else:
                call_internal_api(script.config, 'update_user_agent_stats',
                    application_id=application_id, date=date,
                    user_agent=user_agent, ip=ip, count=count)
            redis.hincrby('lookups.ua', key, -count)


run_script(main)

