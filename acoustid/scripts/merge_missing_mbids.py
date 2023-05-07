#!/usr/bin/env python

# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging

from acoustid.data.track import merge_missing_mbids

logger = logging.getLogger(__name__)


def run_merge_missing_mbids(script, opts, args):
    if script.config.cluster.role != "master":
        logger.info("Not running merge_missing_mbids in slave mode")
        return

    conn = script.db_engines["app"].connect()
    with conn.begin():
        merge_missing_mbids(conn)
