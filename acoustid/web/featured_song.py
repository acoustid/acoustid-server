"""The song whose fingerprint is drawn on the home page.

A random, reasonably popular song from the database, picked once an hour and
shared by every page view until then. When none can be found, for example in
an empty database, the page falls back to a song that is always available.
"""

import datetime
import random
from typing import Any, Optional

from sqlalchemy import sql

from acoustid import tables as schema
from acoustid.data.musicbrainz import lookup_recording_metadata
from acoustid.web import db
from acoustid.web.stats_cache import cached_json

FEATURED_SONG_KEY = "web:home:featured_song"
FEATURED_SONG_TTL = datetime.timedelta(hours=1)

# Fingerprints submitted by a few people, so the song is likely real and
# known, and covering the two minutes the page talks about. A fingerprint
# frame is about 0.124 seconds, and the length is that of the whole file.
MIN_SUBMISSIONS = 5
MIN_LENGTH = 120
MIN_FRAMES = 900

# How many random starting points to try, and how many fingerprints to look
# at from each, before giving up and using the fallback. Each attempt only
# looks at a window of fingerprint IDs, so a start near the end of the table,
# where few fingerprints have enough submissions yet, can't turn into a scan
# of everything after it.
ATTEMPTS = 5
CANDIDATES_PER_ATTEMPT = 20
ID_WINDOW = 20000

# The page draws the first two minutes, so that is all that is stored.
FRAMES_SHOWN = 948

FALLBACK_SONG = {
    "track": "9ff43b6a-4f16-427c-93c2-92307ca505e0",
    "name": "Lower Your Eyelids to Die With the Sun",
    "artist": "M83",
}


def pick_random_song() -> Optional[dict[str, Any]]:
    """A random song with its fingerprint, or None if none was found.

    Starts at a random fingerprint ID and takes the next suitable ones,
    which is a short scan of the primary key rather than a random sort of
    the whole table.
    """
    fingerprint_db = db.get_fingerprint_db()
    max_id = fingerprint_db.execute(
        sql.select(sql.func.max(schema.fingerprint.c.id))
    ).scalar()
    if not max_id:
        return None

    src = schema.fingerprint.join(
        schema.track, schema.track.c.id == schema.fingerprint.c.track_id
    ).join(
        schema.track_mbid,
        sql.and_(
            schema.track_mbid.c.track_id == schema.fingerprint.c.track_id,
            schema.track_mbid.c.disabled.is_(False),
        ),
    )
    for _ in range(ATTEMPTS):
        start = random.randint(1, max(1, max_id - ID_WINDOW))
        query = (
            sql.select(
                schema.fingerprint.c.fingerprint[1:FRAMES_SHOWN].label("fingerprint"),
                schema.track.c.gid,
                schema.track_mbid.c.mbid,
            )
            .select_from(src)
            .where(
                schema.fingerprint.c.id.between(start, start + ID_WINDOW),
                schema.fingerprint.c.submission_count >= MIN_SUBMISSIONS,
                schema.fingerprint.c.length >= MIN_LENGTH,
                sql.func.array_length(schema.fingerprint.c.fingerprint, 1)
                >= MIN_FRAMES,
                schema.track.c.new_id.is_(None),
            )
            .order_by(schema.fingerprint.c.id)
            .limit(CANDIDATES_PER_ATTEMPT)
        )
        rows = fingerprint_db.execute(query).fetchall()
        if not rows:
            continue
        metadata = {
            str(k): v
            for k, v in lookup_recording_metadata(
                db.get_musicbrainz_db(), [row.mbid for row in rows]
            ).items()
        }
        for row in rows:
            recording = metadata.get(str(row.mbid))
            if recording and recording.get("name") and recording.get("artist_name"):
                return {
                    "track": str(row.gid),
                    "name": recording["name"],
                    "artist": recording["artist_name"],
                    "fingerprint": list(row.fingerprint),
                }
    return None


def get_featured_song(fallback_fingerprint: list[int]) -> dict[str, Any]:
    """The song for the home page, changing once an hour."""

    song = cached_json(
        FEATURED_SONG_KEY,
        pick_random_song,
        default=None,
        ttl=FEATURED_SONG_TTL,
        single_flight=True,
    )
    if not song:
        return dict(FALLBACK_SONG, fingerprint=fallback_fingerprint)
    return song
