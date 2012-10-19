#!/usr/bin/env python

# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import json
from acoustid.script import run_script
from acoustid.data.submission import import_queued_submissions

logger = logging.getLogger(__name__)


def main(script, opts, args):
    channel = script.redis.pubsub()
    channel.subscribe('channel.submissions')
    for message in channel.listen():
        ids = json.loads(message)
        logger.debug('Got notified about %s new submissions', len(ids))
        #conn = script.engine.connect()
        #import_queued_submissions(conn, limit=300, index=script.index)


run_script(main)

