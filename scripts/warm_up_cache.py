#!/usr/bin/env python

# Copyright (C) 2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import time
import random
from acoustid.script import run_script
from acoustid.data.fingerprint import FingerprintSearcher
from acoustid.data.track import lookup_mbids
from acoustid.data.musicbrainz import lookup_metadata


def main(script, opts, args):
    conn = script.engine.connect()
    min_id, max_id = conn.execute("SELECT min(id), max(id) FROM fingerprint").fetchone()
    print min_id, max_id
    while True:
        id = random.randint(min_id, max_id)
        row = conn.execute("SELECT fingerprint, length FROM fingerprint WHERE id = %s", (id,)).fetchone()
        if row is None:
            continue
        fingerprint, length = row
        for i in range(1):
            t0 = time.time()
            for i in range(len(fingerprint)):
                fingerprint[i] ^= random.getrandbits(2) << random.randint(0, 20)
            searcher = FingerprintSearcher(script.engine, script.index)
            matches = searcher.search(fingerprint, length + random.randint(-8, 8))
            track_ids = [r[1] for r in matches]
            track_mbid_map = lookup_mbids(conn, track_ids)
            mbids = set()
            for track_id, track_mbids in track_mbid_map.iteritems():
                for mbid, sources in track_mbids:
                    mbids.add(mbid)
            metadata = lookup_metadata(conn, mbids, load_releases=True, load_release_groups=True)
            print "Searching for ID", id, len(matches), time.time() - t0
        time.sleep(1)

run_script(main)

