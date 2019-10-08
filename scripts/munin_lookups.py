#!/usr/bin/env python

# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
from acoustid.script import run_script


def main(script, opts, args):
    if args and args[0] == 'config':
        print 'graph_title Fingerprint lookup rate'
        print 'graph_vlabel lookups/s'
        print 'graph_args --base 1000 -l 0'
        print 'graph_category acoustid'
        print 'hits.label Hits'
        print 'hits.draw LINE2'
        print 'hits.type DERIVE'
        print 'hits.min 0'
        print 'misses.label Misses'
        print 'misses.draw LINE2'
        print 'misses.type DERIVE'
        print 'misses.min 0'
        print 'total.label Total'
        print 'total.draw LINE2'
        print 'total.type DERIVE'
        print 'total.min 0'
        return
    today = datetime.date.today().isoformat()
    redis = script.redis
    total = {'hit': 0, 'miss': 0}
    for key, count in redis.hgetall('lookups').items():
        date, hour, application_id, type = key.split(':')
        if date != today:
            continue
        total[type] += int(count)
    print 'hits.value', total['hit']
    print 'misses.value', total['miss']
    print 'total.value', total['miss'] + total['hit']


run_script(main)

