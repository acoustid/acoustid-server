#!/usr/bin/env python

# Copyright (C) 2012-2013 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import json
import logging
import socket
import time
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from acoustid.data.submission import import_queued_submissions
from acoustid.indexclient import IndexClientConnectError
from acoustid.script import Script

logger = logging.getLogger(__file__)


def is_transient_import_error(ex: BaseException) -> bool:
    """Is this an error that costs one pass but no work?

    The importer retries in a loop, and both of these leave the queue intact:
    the statement timeout rolls back the transaction so the pending rows
    survive, and a timed out index connection is reconnected next time. How
    often they happen is a question for the importer metrics; an individual
    occurrence is not something anyone can act on.

    Errors that will not fix themselves on a retry are not included, however
    often the loop runs into them.
    """
    if isinstance(ex, IndexClientConnectError):
        # Only a timeout is transient. A refused connection or a name that does
        # not resolve usually means the endpoint is wrong, and a misconfigured
        # deployment has to stay visible however often it retries.
        return isinstance(ex.__cause__, socket.timeout)
    if isinstance(ex, OperationalError):
        return "canceling statement due to statement timeout" in str(ex)
    return False


def do_import(script: Script, limit: int = 100) -> int:
    total_count = 0
    count = 1
    while count > 0 and total_count < limit:
        with script.context() as ctx:
            if ctx.statsd is not None:
                ctx.statsd.incr("importer_running", 1)
            ingest_db = ctx.db.get_ingest_db()
            app_db = ctx.db.get_app_db()
            fingerprint_db = ctx.db.get_fingerprint_db()

            timeout_ms = 60 * 1000
            ingest_db.execute(text("SET LOCAL enable_seqscan TO off"))
            ingest_db.execute(
                text("SET LOCAL statement_timeout TO :timeout"),
                {"timeout": timeout_ms},
            )
            app_db.execute(
                text("SET LOCAL statement_timeout TO :timeout"),
                {"timeout": timeout_ms},
            )
            fingerprint_db.execute(
                text("SET LOCAL statement_timeout TO :timeout"),
                {"timeout": timeout_ms},
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
        except Exception as ex:
            if is_transient_import_error(ex):
                logger.warning("Could not import submissions this pass", exc_info=True)
            else:
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
