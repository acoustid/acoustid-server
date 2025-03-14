#!/usr/bin/env python

# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
import logging
from contextlib import ExitStack
from typing import cast
from uuid import UUID

from acoustid.data.account import lookup_account_id_by_name
from acoustid.data.musicbrainz import get_last_replication_date
from acoustid.data.track import disable_mbid, merge_missing_mbid
from acoustid.db import (
    AppDB,
    FingerprintDB,
    IngestDB,
    MusicBrainzDB,
    pg_try_advisory_xact_lock,
)
from acoustid.script import Script

logger = logging.getLogger(__name__)


def run_merge_missing_mbid(script: Script, mbid: str) -> None:
    if script.config.cluster.role != "master":
        logger.info("Not running merge_missing_mbid in replica mode")
        return

    with ExitStack() as stack:
        redis = script.get_redis()
        cache_key = f"unknown_mbid:{mbid}"

        fingerprint_db_conn = stack.enter_context(
            script.db_engines["fingerprint"].connect()
        )
        fingerprint_db = cast(FingerprintDB, fingerprint_db_conn)
        fingerprint_db_txn = stack.enter_context(fingerprint_db.begin_twophase())

        ingest_db_conn = stack.enter_context(script.db_engines["ingest"].connect())
        ingest_db = cast(IngestDB, ingest_db_conn)
        ingest_db_txn = stack.enter_context(ingest_db.begin_twophase())

        musicbrainz_db_conn = stack.enter_context(
            script.db_engines["musicbrainz"].connect()
        )
        musicbrainz_db = cast(MusicBrainzDB, musicbrainz_db_conn)

        app_db_conn = stack.enter_context(script.db_engines["app"].connect())
        app_db = cast(AppDB, app_db_conn)

        if not pg_try_advisory_xact_lock(fingerprint_db, "merge_missing_mbid", mbid):
            logger.info("MBID %s is already being merged", mbid)
            return

        handled = merge_missing_mbid(
            fingerprint_db=fingerprint_db,
            ingest_db=ingest_db,
            musicbrainz_db=musicbrainz_db,
            old_mbid=UUID(mbid),
        )
        if handled:
            fingerprint_db_txn.prepare()
            ingest_db_txn.prepare()
            fingerprint_db_txn.commit()
            ingest_db_txn.commit()
            return

        unknown_since: datetime.datetime | None = None
        unknown_since_str = redis.get(cache_key)
        if unknown_since_str:
            try:
                unknown_since = datetime.datetime.fromisoformat(
                    unknown_since_str.decode()
                )
            except Exception:
                logger.warning("Failed to parse unknown_since date for MBID %s", mbid)

        now = get_last_replication_date(musicbrainz_db)
        if unknown_since is None:
            unknown_since = now
            redis.set(cache_key, now.isoformat())
            return

        if now - unknown_since < datetime.timedelta(days=7):
            return

        logger.info("MBID %s has been unknown for too long, disabling", mbid)
        acoustid_bot_id = lookup_account_id_by_name(app_db, "acoustid_bot")
        if acoustid_bot_id is None:
            logger.error("acoustid_bot account not found")
            return

        disable_mbid(
            fingerprint_db=fingerprint_db,
            ingest_db=ingest_db,
            mbid=mbid,
            account_id=acoustid_bot_id,
            note="MBID has been unknown for too long",
        )
        fingerprint_db_txn.prepare()
        ingest_db_txn.prepare()
        fingerprint_db_txn.commit()
        ingest_db_txn.commit()
