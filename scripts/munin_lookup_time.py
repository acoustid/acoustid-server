#!/usr/bin/env python

# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
from acoustid.script import run_script


def main(script, opts, args):
    if args and args[0] == 'config':
        print 'graph_title Fingerprint lookup time'
        print 'graph_vlabel ms'
        print 'graph_args --base 1000 -l 0'
        print 'graph_scale no'
        print 'graph_category acoustid'
        print 'time.label Average lookup time (5m)'
        print 'time.draw LINE2'
        print 'time.type GAUGE'
        return
    redis = script.redis
    one_minute = datetime.timedelta(minutes=1)
    total_ms = 0.0
    total_count = 0
    time = datetime.datetime.now() - one_minute
    for i in range(5):
        key = time.strftime('%Y-%m-%d:%H:%M')
        ms = redis.hget('lookups.time.ms', key)
        count = redis.hget('lookups.time.count', key)
        if ms and count:
            total_ms += int(ms)
            total_count += int(count)
        time -= one_minute
    if not total_count:
        total_ms = 0.0
        total_count = 1
    print 'time.value', total_ms / total_count


run_script(main)

