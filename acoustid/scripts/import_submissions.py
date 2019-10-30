#!/usr/bin/env python

# Copyright (C) 2012-2013 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import json
import logging
import time
from acoustid.script import Script
from acoustid.data.submission import import_queued_submissions

logger = logging.getLogger(__file__)


def do_import(script):
    # type: (Script) -> None
    count = 1
    while count > 0:
        with script.context() as ctx:
            ingest_db = ctx.db.get_ingest_db()
            app_db = ctx.db.get_app_db()
            fingerprint_db = ctx.db.get_fingerprint_db()
            count = import_queued_submissions(ingest_db, app_db, fingerprint_db, ctx.index, limit=10)
            ctx.db.session.commit()


def run_import_on_master(script):
    # type: (Script) -> None
    logger.info('Importer running in master mode')
    # listen for new submissins and import them as they come
    channel = script.redis.pubsub()
    channel.subscribe('channel.submissions')
    for message in channel.listen():
        if message['type'] != 'message':
            continue
        try:
            ids = json.loads(message['data'])
        except Exception:
            logger.exception('Invalid notification message: %r', message)
            ids = []
        logger.debug('Got notified about %s new submissions', len(ids))
        do_import(script)
        logger.debug('Waiting for the next event...')


def run_import_on_slave(script):
    # type: (Script) -> None
    logger.info('Importer running in slave mode, not doing anything')
    while True:
        delay = 60
        logger.debug('Waiting %d seconds...', delay)
        time.sleep(delay)


def run_import(script):
    # type: (Script) -> None
    if script.config.cluster.role == 'master':
        run_import_on_master(script)
    else:
        run_import_on_slave(script)
