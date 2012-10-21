#!/usr/bin/env python

# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import json
import logging
from contextlib import closing
from acoustid.script import run_script
from acoustid.data.submission import import_queued_submissions
from acoustid.data.fingerprint import update_fingerprint_index

logger = logging.getLogger(__file__)


def do_import(script, index_first=False):
    with closing(script.engine.connect()) as db:
        if index_first:
            update_fingerprint_index(db, script.index)
        while True:
            count = import_queued_submissions(db, script.index)
            if not count:
                break
            update_fingerprint_index(db, script.index)


def main(script, opts, args):
    # first make sure the index is in sync with the database and
    # import already queued submissions
    do_import(script, index_first=True)
    # listen for new submissins and import them as they come
    channel = script.redis.pubsub()
    channel.subscribe('channel.submissions')
    for message in channel.listen():
        ids = json.loads(message['data'])
        logger.debug('Got notified about %s new submissions', len(ids))
        do_import(script)


run_script(main)

