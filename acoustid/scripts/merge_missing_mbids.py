#!/usr/bin/env python

# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
import logging
import zlib
from contextlib import ExitStack

import sqlalchemy as sa

from acoustid.data.musicbrainz import get_last_replication_date
from acoustid.data.track import merge_missing_mbid
from acoustid.script import Script

logger = logging.getLogger(__name__)


def try_lock(db: sa.engine.Connection, name: str, params: str) -> bool:
    lock_id1 = zlib.crc32(name.encode()) & 0x7FFFFFFF
    lock_id2 = zlib.crc32(params.encode()) & 0x7FFFFFFF
    return db.execute(
        sa.text("SELECT pg_try_advisory_xact_lock(:lock_id1, :lock_id2)"),
        {"lock_id1": lock_id1, "lock_id2": lock_id2},
    ).scalar()


def run_merge_missing_mbid(script: Script, mbid: str) -> None:
    if script.config.cluster.role != "master":
        logger.info("Not running merge_missing_mbid in replica mode")
        return

    with ExitStack() as stack:
        redis = script.get_redis()
        cache_key = "unknown_mbid:{}".format(mbid)

        fingerprint_db = stack.enter_context(script.db_engines["fingerprint"].begin())
        if not try_lock(fingerprint_db, "merge_missing_mbid", mbid):
            logger.info("MBID %s is already being merged", mbid)
            return

        ingest_db = stack.enter_context(script.db_engines["ingest"].begin())
        musicbrainz_db = stack.enter_context(script.db_engines["musicbrainz"].begin())

        handled = merge_missing_mbid(
            fingerprint_db=fingerprint_db,
            ingest_db=ingest_db,
            musicbrainz_db=musicbrainz_db,
            old_mbid=mbid,
        )
        if handled:
            return

        unknown_since: datetime.datetime | None = None
        unknown_since_str = redis.get(cache_key)
        if unknown_since_str:
            try:
                unknown_since = datetime.datetime.fromisoformat(
                    unknown_since_str.decode()
                )
            except Exception:
                pass

        now = get_last_replication_date(musicbrainz_db)
        if unknown_since is None:
            unknown_since = now
            redis.set(cache_key, now.isoformat())

        if now - unknown_since < datetime.timedelta(days=7):
            return

        logger.info("MBID %s has been unknown for too long, disabling", mbid)
