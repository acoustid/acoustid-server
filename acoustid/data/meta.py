# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import json
import logging
import re
import time
import uuid
from collections import OrderedDict
from collections.abc import Iterable
from typing import Any

import six
from sqlalchemy import sql
from sqlalchemy.dialects.postgresql import insert

from acoustid import tables as schema
from acoustid.db import FingerprintDB

logger = logging.getLogger(__name__)

meta_fields = (
    "track",
    "artist",
    "album",
    "album_artist",
    "track_no",
    "disc_no",
    "year",
)

meta_gid_ns = uuid.UUID("3b3bd228-5d2c-11ea-b498-60f67731bf41")


def fix_meta(values: dict[str, Any]) -> dict[str, Any]:
    values = dict(values)

    for key, value in values.items():
        if isinstance(value, str):
            values[key] = re.sub(r"(\s|\x00)+", " ", value)

    track_no = values.get("track_no", None)
    if track_no:
        if track_no > 10000:
            del values["track_no"]

    disc_no = values.get("disc_no", None)
    if disc_no:
        if disc_no > 10000:
            del values["disc_no"]

    return values


def generate_meta_gid(values: dict[str, Any]) -> uuid.UUID:
    content_hash_items = OrderedDict()
    for name in meta_fields:
        value = values.get(name)
        if value:
            content_hash_items[name] = value
    content_hash_source = json.dumps(
        content_hash_items, ensure_ascii=False, separators=(",", ":")
    )
    return uuid.uuid5(meta_gid_ns, content_hash_source)


def find_meta_id(conn: FingerprintDB, gid: uuid.UUID) -> int | None:
    query = sql.select(schema.meta.c.id).where(schema.meta.c.gid == gid)
    return conn.execute(query).scalar()


def find_or_insert_meta(
    conn: FingerprintDB, values: dict[str, Any]
) -> tuple[int, uuid.UUID]:
    meta_gid = generate_meta_gid(values)

    max_retries = 3
    retry = 0
    while True:
        meta_id = find_meta_id(conn, meta_gid)
        if meta_id is not None:
            return meta_id, meta_gid

        insert_stmt = (
            insert(schema.meta)
            .values(
                gid=meta_gid,
                created=sql.func.current_timestamp(),
                **values,
            )
            .on_conflict_do_nothing()  # index_elements=[schema.meta.c.gid],
            .returning(schema.meta.c.id)
        )
        meta_id = conn.execute(insert_stmt).scalar()
        if meta_id is not None:
            logger.debug(
                "Inserted meta %d with gid %s and values %r",
                meta_id,
                meta_gid,
                values,
            )
            return meta_id, meta_gid

        time.sleep(0.05 * retry)

        retry += 1
        if retry == max_retries:
            raise RuntimeError("Failed to insert meta")


def insert_meta(conn: FingerprintDB, values: dict[str, Any]) -> tuple[int, uuid.UUID]:
    gid = generate_meta_gid(values)
    if "gid" not in values:
        values["gid"] = gid
    insert_stmt = schema.meta.insert().values(
        created=sql.func.current_timestamp(), **values
    )
    id = conn.execute(insert_stmt).inserted_primary_key[0]
    logger.debug("Inserted meta %d with values %r", id, values)
    return id, gid


def check_meta_id(
    fingerprint_db: FingerprintDB, meta_id: int
) -> tuple[bool, uuid.UUID | None]:
    query = sql.select(schema.meta.c.id, schema.meta.c.gid).where(
        schema.meta.c.id == meta_id
    )
    row = fingerprint_db.execute(query).first()
    if row is None:
        return False, None
    return True, row.gid


def lookup_meta(conn: FingerprintDB, meta_ids: Iterable[int]) -> list[dict[str, Any]]:
    if not meta_ids:
        return []
    query = sql.select(schema.meta).where(schema.meta.c.id.in_(meta_ids))
    results = []
    for row in conn.execute(query):
        result = {
            "_no_ids": True,
            "recording_id": row.id,
            "recording_title": row.track,
            "recording_artists": [],
            "recording_duration": None,
            "track_id": row.id,
            "track_position": row.track_no,
            "track_title": row.track,
            "track_artists": [],
            "track_duration": None,
            "medium_position": row.disc_no,
            "medium_format": None,
            "medium_title": None,
            "medium_track_count": None,
            "release_rid": row.id,
            "release_id": row.id,
            "release_title": row.album,
            "release_artists": [],
            "release_medium_count": None,
            "release_track_count": None,
            "release_events": [
                {
                    "release_date_year": row.year,
                    "release_date_month": None,
                    "release_date_day": None,
                    "release_country": "",
                }
            ],
            "release_group_id": row.id,
            "release_group_title": row.album,
            "release_group_artists": [],
            "release_group_primary_type": None,
            "release_group_secondary_types": [],
        }
        if row.artist:
            result["recording_artists"].append(row.artist)
            result["track_artists"].append(row.artist)
        if row.album_artist:
            result["release_artists"].append(row.album_artist)
            result["release_group_artists"].append(row.album_artist)
        results.append(result)
    return results
