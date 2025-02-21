#!/usr/bin/env python

# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from contextlib import ExitStack

from acoustid.data.track import merge_missing_mbid
from acoustid.script import Script

logger = logging.getLogger(__name__)


def run_merge_missing_mbid(script: Script, mbid: str):
    if script.config.cluster.role != "master":
        logger.info("Not running merge_missing_mbid in replica mode")
        return

    with ExitStack() as stack:
        fingerprint_db = stack.enter_context(script.db_engines["fingerprint"].begin())
        ingest_db = stack.enter_context(script.db_engines["ingest"].begin())
        musicbrainz_db = stack.enter_context(script.db_engines["musicbrainz"].begin())
        merge_missing_mbid(fingerprint_db, ingest_db, musicbrainz_db, mbid)
