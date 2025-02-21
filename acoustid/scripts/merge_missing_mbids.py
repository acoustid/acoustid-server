#!/usr/bin/env python

# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
import zlib
from contextlib import ExitStack

import sqlalchemy as sa

from acoustid.data.track import merge_missing_mbid
from acoustid.script import Script

logger = logging.getLogger(__name__)


def try_lock(db: sa.engine.Connection, name: str, params: str) -> bool:
    lock_id1 = zlib.crc32(name.encode())
    lock_id2 = zlib.crc32(params.encode())
    return db.execute(
        sa.text("SELECT pg_try_advisory_xact_lock(:lock_id1, :lock_id2)"),
        {"lock_id1": lock_id1, "lock_id2": lock_id2},
    ).scalar()


def run_merge_missing_mbid(script: Script, mbid: str):
    if script.config.cluster.role != "master":
        logger.info("Not running merge_missing_mbid in replica mode")
        return

    with ExitStack() as stack:
        fingerprint_db = stack.enter_context(script.db_engines["fingerprint"].begin())
        if not try_lock(fingerprint_db, "merge_missing_mbid", mbid):
            logger.info("MBID %s is already being merged", mbid)
            return

        ingest_db = stack.enter_context(script.db_engines["ingest"].begin())
        musicbrainz_db = stack.enter_context(script.db_engines["musicbrainz"].begin())

        merge_missing_mbid(
            fingerprint_db=fingerprint_db,
            ingest_db=ingest_db,
            musicbrainz_db=musicbrainz_db,
            old_mbid=mbid,
        )
