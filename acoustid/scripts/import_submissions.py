#!/usr/bin/env python

# Copyright (C) 2012-2013 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import json
import logging
import time
from typing import Any, Dict, Optional

from sqlalchemy import text

from acoustid.data.submission import import_queued_submissions
from acoustid.script import Script

logger = logging.getLogger(__file__)


def do_import(script: Script, limit: int = 100) -> int:
    total_count = 0
    count = 1
    while count > 0 and count < limit:
        with script.context() as ctx:
            if ctx.statsd is not None:
                ctx.statsd.incr("importer_running", 1)
            ingest_db = ctx.db.get_ingest_db()
            app_db = ctx.db.get_app_db()
            fingerprint_db = ctx.db.get_fingerprint_db()

            timeout_ms = 20 * 1000
            ingest_db.execute(text("SET LOCAL enable_seqscan TO off"))
            ingest_db.execute(
                text("SET LOCAL statement_timeout TO :timeout"), {"timeout": timeout_ms}
            )
            app_db.execute(
                text("SET LOCAL statement_timeout TO :timeout"), {"timeout": timeout_ms}
            )
            fingerprint_db.execute(
                text("SET LOCAL statement_timeout TO :timeout"), {"timeout": timeout_ms}
            )

            count = import_queued_submissions(
                ingest_db, app_db, fingerprint_db, ctx.index, limit=1
            )
            ctx.db.session.commit()

            if ctx.statsd is not None:
                ctx.statsd.incr("imported_submissions", count)

            total_count += count

    return total_count


def run_import_on_master(script):
    # type: (Script) -> None
    logger.info("Importer running in master mode")
    # listen for new submissins and import them as they come

    min_delay = 1.0
    max_delay = 10.0
    delay_update_coefficient = 1.3

    delay = min_delay

    while True:
        try:
            imported = do_import(script)
            logger.info("Imported %d submissions", imported)
        except Exception:
            logger.exception("Failed to import submissions")
            imported = 0

        if imported == 0:
            delay = min(delay * delay_update_coefficient, max_delay)
        else:
            delay = max(delay / delay_update_coefficient, min_delay)

        logger.debug("Waiting %s seconds...", delay)
        time.sleep(delay)


def run_import_on_slave(script):
    # type: (Script) -> None
    logger.info("Importer running in slave mode, not doing anything")
    while True:
        delay = 60
        logger.debug("Waiting %d seconds...", delay)
        time.sleep(delay)


def run_import(script):
    # type: (Script) -> None
    script.setup_sentry(component="import")
    if script.config.cluster.role == "master":
        run_import_on_master(script)
    else:
        run_import_on_slave(script)
