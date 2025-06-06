import uuid
from typing import TypedDict

from sqlalchemy import sql

import acoustid.tables as schema

from .db import FingerprintDB


class TrackInfo(TypedDict):
    gid: uuid.UUID
    disabled: bool


async def list_tracks_by_mbid(
    db: FingerprintDB, mbid: uuid.UUID, include_disabled: bool = False
) -> list[TrackInfo]:
    """List tracks by MBID."""
    stmt = (
        sql.select(schema.track.c.gid, schema.track_mbid.c.disabled)
        .select_from(schema.track_mbid)
        .join(schema.track, schema.track.c.id == schema.track_mbid.c.track_id)
        .where(schema.track_mbid.c.mbid == mbid)
    )
    if not include_disabled:
        stmt = stmt.where(schema.track_mbid.c.disabled == sql.false())
    rows = await db.execute(stmt)
    return [TrackInfo(gid=row.gid, disabled=row.disabled) for row in rows]


async def list_track_by_fingerprint_id(
    db: FingerprintDB, fingerprint_id: int
) -> list[TrackInfo]:
    """List tracks by fingerprint ID."""
    stmt = (
        sql.select(schema.track.c.gid)
        .select_from(schema.fingerprint)
        .join(schema.track, schema.track.c.id == schema.fingerprint.c.track_id)
        .where(schema.fingerprint.c.id == fingerprint_id)
    )
    rows = await db.execute(stmt)
    return [TrackInfo(gid=row.gid, disabled=False) for row in rows]
