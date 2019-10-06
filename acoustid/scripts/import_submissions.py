#!/usr/bin/env python

# Copyright (C) 2012-2013 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import json
import logging
import time
from acoustid.script import Script
from acoustid.data.submission import import_queued_submissions
from acoustid.data.fingerprint import update_fingerprint_index

logger = logging.getLogger(__file__)


def do_import(script, index_first=False, only_index=False):
    # type: (Script, bool, bool) -> None
    with script.context() as ctx:
        fingerprint_db = ctx.db.get_fingerprint_db()
        if index_first:
            with ctx.index.connect() as index:
                update_fingerprint_index(fingerprint_db, index)
        if not only_index:
            app_db = ctx.db.get_app_db()
            ingest_db = ctx.db.get_ingest_db()
            while True:
                count = import_queued_submissions(ingest_db, app_db, fingerprint_db, ctx.index, limit=10)
                if not count:
                    break
                with ctx.index.connect() as index:
                    update_fingerprint_index(fingerprint_db, index)
        ctx.db.session.commit()


def run_import_on_master(script):
    logger.info('Importer running in master mode')
    # first make sure the index is in sync with the database and
    # import already queued submissions
    do_import(script, index_first=True)
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
    logger.info('Importer running in slave mode, only updating the index')
    # import new fingerprints to the index every 15 seconds
    while True:
        started = time.time()
        do_import(script, index_first=True, only_index=True)
        delay = 15 - time.time() + started
        if delay > 0:
            logger.debug('Waiting %d seconds...', delay)
            time.sleep(delay)


def run_import(script):
    if script.config.cluster.role == 'master':
        run_import_on_master(script)
    else:
        run_import_on_slave(script)
