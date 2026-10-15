#!/usr/bin/env python

# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Extract training data for the fingerprint barcode colors.

Writes two JSON Lines files into the output directory:

random.jsonl
    Fingerprints picked uniformly at random, one per line:
    {"id": ..., "track_id": ..., "fingerprint": [...]}

recordings.jsonl
    MusicBrainz recordings linked to two or more AcoustIDs, one per line,
    with the most submitted fingerprint of each AcoustID, the way the
    recording page shows them (most submitted AcoustID first):
    {"mbid": ..., "tracks": [{"track_id": ..., "gid": ..., "disabled": ...,
     "submission_count": ..., "fingerprint_id": ..., "fingerprint": [...]}]}

Only the first THUMBNAIL_FRAMES frames of each fingerprint are kept, the
same part the thumbnails are drawn from. It only reads from the database.

    python scripts/barcode/extract.py -c acoustid.conf -o barcode-data \\
        --fingerprints 20000 --recordings 5000
"""

import json
import logging
import os
import random
from typing import Any, Iterator

from sqlalchemy import sql

from acoustid import tables as schema
from acoustid.script import run_script
from acoustid.web.views.metadata import MAX_FINGERPRINT_THUMBNAILS, THUMBNAIL_FRAMES

logger = logging.getLogger(__name__)

BATCH = 1000
# Batches in a row that add no recording before giving up, for databases
# with fewer qualifying recordings than were asked for.
MAX_IDLE_BATCHES = 50


def sample_ids(conn: Any, table: Any) -> Iterator[list[int]]:
    """Batches of random ids from 1 to max(id); some of them may not exist."""
    max_id = conn.execute(sql.select(sql.func.max(table.c.id))).scalar_one()
    while True:
        yield random.sample(range(1, max_id + 1), min(BATCH, max_id))


def extract_random(conn: Any, path: str, count: int) -> None:
    fp = schema.fingerprint
    written = 0
    with open(path, "w") as out:
        for ids in sample_ids(conn, fp):
            query = sql.select(
                fp.c.id,
                fp.c.track_id,
                fp.c.fingerprint[1:THUMBNAIL_FRAMES].label("fingerprint"),
            ).where(fp.c.id.in_(ids))
            for row in conn.execute(query):
                out.write(json.dumps(dict(row._mapping)) + "\n")
                written += 1
                if written >= count:
                    logger.info("Wrote %d random fingerprints to %s", written, path)
                    return


def extract_recordings(conn: Any, path: str, count: int) -> None:
    tm = schema.track_mbid
    fp = schema.fingerprint
    seen: set[str] = set()
    written = 0
    idle = 0
    with open(path, "w") as out:
        # Sampling links rather than recordings favours recordings with many
        # AcoustIDs, which are the pages the barcodes are for.
        for ids in sample_ids(conn, tm):
            before = written
            mbids = {
                str(m)
                for m in conn.execute(
                    sql.select(tm.c.mbid).where(tm.c.id.in_(ids))
                ).scalars()
            }
            for mbid in sorted(mbids - seen):
                seen.add(mbid)
                tracks = [
                    dict(row._mapping, gid=str(row.gid))
                    for row in conn.execute(
                        sql.select(
                            schema.track.c.id.label("track_id"),
                            schema.track.c.gid,
                            tm.c.disabled,
                            tm.c.submission_count,
                        )
                        .select_from(
                            tm.join(schema.track, schema.track.c.id == tm.c.track_id)
                        )
                        .where(tm.c.mbid == mbid)
                        .order_by(tm.c.submission_count.desc())
                    )
                ]
                if not 2 <= len(tracks) <= MAX_FINGERPRINT_THUMBNAILS:
                    continue
                representative = {
                    row.track_id: row
                    for row in conn.execute(
                        sql.select(
                            fp.c.track_id,
                            fp.c.id,
                            fp.c.fingerprint[1:THUMBNAIL_FRAMES].label("fingerprint"),
                        )
                        .where(fp.c.track_id.in_([t["track_id"] for t in tracks]))
                        .distinct(fp.c.track_id)
                        .order_by(fp.c.track_id, fp.c.submission_count.desc())
                    )
                }
                for t in tracks:
                    row = representative.get(t["track_id"])
                    t["fingerprint_id"] = row.id if row else None
                    t["fingerprint"] = row.fingerprint if row else None
                tracks = [t for t in tracks if t["fingerprint"]]
                if len(tracks) < 2:
                    continue
                out.write(json.dumps({"mbid": mbid, "tracks": tracks}) + "\n")
                written += 1
                if written % 500 == 0:
                    logger.info("%d recordings so far", written)
                if written >= count:
                    logger.info("Wrote %d recordings to %s", written, path)
                    return
            idle = idle + 1 if written == before else 0
            if idle >= MAX_IDLE_BATCHES:
                logger.warning(
                    "Only found %d of %d recordings, wrote them to %s",
                    written,
                    count,
                    path,
                )
                return


def main(script: Any, opts: Any, args: Any) -> None:
    random.seed(opts.seed)
    os.makedirs(opts.output, exist_ok=True)
    with script.db_engines["fingerprint"].connect() as conn:
        extract_random(
            conn, os.path.join(opts.output, "random.jsonl"), opts.fingerprints
        )
        extract_recordings(
            conn, os.path.join(opts.output, "recordings.jsonl"), opts.recordings
        )


def add_options(parser: Any) -> None:
    parser.add_option("-o", "--output", default="barcode-data", help="output directory")
    parser.add_option("--fingerprints", type="int", default=20000)
    parser.add_option("--recordings", type="int", default=5000)
    parser.add_option("--seed", type="int", default=1)


if __name__ == "__main__":
    run_script(main, add_options)
