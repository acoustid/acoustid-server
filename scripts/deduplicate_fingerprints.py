#!/usr/bin/env python

# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import chromaprint
from acoustid.script import run_script
from acoustid.data.track import find_duplicates
from acoustid.data.fingerprint import FingerprintSearcher


def main(script, opts, args):
    conn = script.engine.connect()
    find_duplicates(conn, index=script.index)
    searcher = FingerprintSearcher(conn, index)
    matches = searcher.search(fingerprint['fingerprint'], fingerprint['length'])
    track_gid = None
    for m in matches:
        track_gid = m['track_gid']
        break

run_script(main)

