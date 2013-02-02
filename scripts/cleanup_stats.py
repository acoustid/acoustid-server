#!/usr/bin/env python

# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
from acoustid.script import run_script


def main(script, opts, args):
    two_days_ago = datetime.datetime.now() - datetime.timedelta(days=2)
    last_key = two_days_ago.strftime('%Y-%m-%d:%H:%M')
    redis = script.redis
    tables = ('lookups.time.ms', 'lookups.time.count')
    for table in tables:
        to_delete = []
        for key in redis.hkeys(table):
            if key < last_key:
                to_delete.append(key)
        if to_delete:
            for table in tables:
                for field in to_delete:
                    redis.hdel(table, field)


run_script(main)

