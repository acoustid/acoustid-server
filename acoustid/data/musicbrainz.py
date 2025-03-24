# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
import logging
from collections.abc import Iterable
from typing import Any

from sqlalchemy import sql

from acoustid import tables as schema
from acoustid.db import MusicBrainzDB

logger = logging.getLogger(__name__)


def get_last_replication_date(conn: MusicBrainzDB) -> datetime.datetime:
    last_replication_date = conn.execute(
        sql.select(schema.mb_replication_control.c.last_replication_date)
    ).scalar()
    if last_replication_date is None:
        raise Exception("Failed to get last replication date")
    return last_replication_date


def _load_artists(
    conn: MusicBrainzDB, artist_credit_ids: Iterable[int]
) -> dict[int, list[dict[str, Any]]]:
    if not artist_credit_ids:
        return {}
    src = schema.mb_artist_credit_name
    src = src.join(schema.mb_artist)
    condition = schema.mb_artist_credit_name.c.artist_credit.in_(artist_credit_ids)
    columns = [
        schema.mb_artist_credit_name.c.name,
        schema.mb_artist_credit_name.c.artist_credit,
        schema.mb_artist_credit_name.c.join_phrase,
        schema.mb_artist.c.gid,
    ]
    query = (
        sql.select(*columns)
        .where(condition)
        .select_from(src)
        .order_by(
            schema.mb_artist_credit_name.c.artist_credit,
            schema.mb_artist_credit_name.c.position,
        )
    )
    result: dict[int, list[dict[str, Any]]] = {}
    for row in conn.execute(query):
        ac_data = {
            "id": str(row.gid),
            "name": row.name,
        }
        if row.join_phrase:
            ac_data["joinphrase"] = row.join_phrase
        result.setdefault(row.artist_credit, []).append(ac_data)
    return result


def _load_release_meta(
    conn: MusicBrainzDB, release_ids: Iterable[int]
) -> dict[int, dict[str, Any]]:
    if not release_ids:
        return {}
    src = schema.mb_medium
    condition = schema.mb_medium.c.release.in_(release_ids)
    columns = [
        schema.mb_medium.c.release,
        sql.func.count(schema.mb_medium.c.id).label("release_medium_count"),
        sql.func.sum(schema.mb_medium.c.track_count).label("release_track_count"),
    ]
    query = (
        sql.select(*columns)
        .where(condition)
        .select_from(src)
        .group_by(schema.mb_medium.c.release)
    )
    result = {}
    for row in conn.execute(query):
        result[row.release] = {
            "release_medium_count": row.release_medium_count,
            "release_track_count": row.release_track_count,
        }
    return result


def _load_release_events(
    conn: MusicBrainzDB, release_ids: Iterable[int]
) -> dict[int, list[dict[str, Any]]]:
    if not release_ids:
        return {}
    src1 = schema.mb_release_country
    src = src1.outerjoin(
        schema.mb_iso_3166_1,
        schema.mb_iso_3166_1.c.area == schema.mb_release_country.c.country,
    )
    condition = schema.mb_release_country.c.release.in_(release_ids)
    columns = [
        schema.mb_release_country.c.release,
        schema.mb_iso_3166_1.c.code.label("release_country"),
        schema.mb_release_country.c.date_year.label("release_date_year"),
        schema.mb_release_country.c.date_month.label("release_date_month"),
        schema.mb_release_country.c.date_day.label("release_date_day"),
    ]
    query = sql.select(*columns).where(condition).select_from(src)
    result: dict[int, list[dict[str, Any]]] = {}
    for row in conn.execute(query):
        result.setdefault(row.release, []).append(
            {
                "release_country": row.release_country,
                "release_date_year": row.release_date_year,
                "release_date_month": row.release_date_month,
                "release_date_day": row.release_date_day,
            }
        )
    return result


def _load_release_group_secondary_types(
    conn: MusicBrainzDB, release_group_ids: Iterable[int]
) -> dict[int, list[str]]:
    if not release_group_ids:
        return {}
    src = schema.mb_release_group_secondary_type_join
    src = src.join(
        schema.mb_release_group_secondary_type,
        schema.mb_release_group_secondary_type_join.c.secondary_type
        == schema.mb_release_group_secondary_type.c.id,
    )
    condition = schema.mb_release_group_secondary_type_join.c.release_group.in_(
        release_group_ids
    )
    columns = [
        schema.mb_release_group_secondary_type_join.c.release_group.label(
            "release_group_rid"
        ),
        schema.mb_release_group_secondary_type.c.name.label(
            "release_group_secondary_type"
        ),
    ]
    query = sql.select(*columns).where(condition).select_from(src)
    result: dict[int, list[str]] = {}
    for row in conn.execute(query):
        result.setdefault(row.release_group_rid, []).append(
            row.release_group_secondary_type
        )
    return result


def _load_release_groups(
    conn: MusicBrainzDB, release_group_ids: Iterable[int]
) -> dict[int, dict[str, Any]]:
    if not release_group_ids:
        return {}
    src = schema.mb_release_group
    src = src.outerjoin(
        schema.mb_release_group_primary_type,
        schema.mb_release_group.c.type == schema.mb_release_group_primary_type.c.id,
    )
    condition = schema.mb_release_group.c.id.in_(release_group_ids)
    columns = [
        schema.mb_release_group.c.id.label("release_group_rid"),
        schema.mb_release_group.c.gid.label("release_group_id"),
        schema.mb_release_group.c.name.label("release_group_title"),
        schema.mb_release_group.c.artist_credit.label("release_group_artist_credit"),
        schema.mb_release_group_primary_type.c.name.label("release_group_primary_type"),
    ]
    query = sql.select(*columns).where(condition).select_from(src)
    secondary_types = _load_release_group_secondary_types(conn, release_group_ids)
    result: dict[int, dict[str, Any]] = {}
    for row in conn.execute(query):
        result[row.release_group_rid] = {
            "release_group_id": str(row.release_group_id),
            "release_group_title": row.release_group_title,
            "release_group_artist_credit": row.release_group_artist_credit,
            "release_group_primary_type": row.release_group_primary_type,
            "release_group_secondary_types": secondary_types.get(row.release_group_rid),
        }
    return result


def lookup_metadata(
    conn: MusicBrainzDB,
    recording_ids: Iterable[str],
    load_releases: bool = False,
    load_release_groups: bool = False,
    load_artists: bool = False,
) -> list[dict[str, Any]]:
    if not recording_ids:
        return []
    src = schema.mb_recording
    columns = [
        schema.mb_recording.c.gid.label("recording_id"),
        schema.mb_recording.c.artist_credit.label("recording_artist_credit"),
        schema.mb_recording.c.name.label("recording_title"),
        (schema.mb_recording.c.length / 1000).label("recording_duration"),
    ]
    if load_releases:
        src = src.join(
            schema.mb_track, schema.mb_recording.c.id == schema.mb_track.c.recording
        )
        src = src.join(
            schema.mb_medium, schema.mb_track.c.medium == schema.mb_medium.c.id
        )
        src = src.join(
            schema.mb_release, schema.mb_medium.c.release == schema.mb_release.c.id
        )
        src = src.outerjoin(
            schema.mb_medium_format,
            schema.mb_medium.c.format == schema.mb_medium_format.c.id,
        )
        columns.extend(
            [
                schema.mb_track.c.gid.label("track_id"),
                schema.mb_track.c.position.label("track_position"),
                schema.mb_track.c.name.label("track_title"),
                schema.mb_track.c.artist_credit.label("track_artist_credit"),
                (schema.mb_track.c.length / 1000).label("track_duration"),
                schema.mb_medium.c.position.label("medium_position"),
                schema.mb_medium.c.track_count.label("medium_track_count"),
                schema.mb_medium.c.name.label("medium_title"),
                schema.mb_medium_format.c.name.label("medium_format"),
                schema.mb_release.c.id.label("release_rid"),
                schema.mb_release.c.gid.label("release_id"),
                schema.mb_release.c.name.label("release_title"),
                schema.mb_release.c.artist_credit.label("release_artist_credit"),
                schema.mb_release.c.release_group.label("release_group_rid"),
            ]
        )
    condition = schema.mb_recording.c.gid.in_(recording_ids)
    query = sql.select(*columns).where(condition).select_from(src)
    results: list[dict[str, Any]] = []
    artist_credit_ids = set()
    release_ids = set()
    release_group_ids = set()
    for row in conn.execute(query):
        r = dict(row._mapping)
        r["release_id"] = str(r["release_id"])
        r["recording_id"] = str(r["recording_id"])
        results.append(r)
        artist_credit_ids.add(row.recording_artist_credit)
        if load_releases:
            release_ids.add(row.release_rid)
            artist_credit_ids.add(row.release_artist_credit)
            artist_credit_ids.add(row.track_artist_credit)
            if load_release_groups:
                release_group_ids.add(row.release_group_rid)

    if load_releases:
        releases = _load_release_meta(conn, release_ids)
        release_events = _load_release_events(conn, release_ids)
        for row2 in results:
            r_id = row2.pop("release_rid")
            row2.update(releases[r_id])
            row2["release_events"] = release_events.get(r_id, {})

        if load_release_groups:
            release_groups = _load_release_groups(conn, release_group_ids)
            for row2 in results:
                rg_id = row2.pop("release_group_rid")
                row2.update(release_groups[rg_id])
                artist_credit_ids.add(row2["release_group_artist_credit"])

    artists = _load_artists(conn, artist_credit_ids)
    for row2 in results:
        row2["recording_artists"] = artists[row2.pop("recording_artist_credit")]
        if load_releases:
            row2["release_artists"] = artists[row2.pop("release_artist_credit")]
            row2["track_artists"] = artists[row2.pop("track_artist_credit")]
            if load_release_groups:
                row2["release_group_artists"] = artists[
                    row2.pop("release_group_artist_credit")
                ]
    return results


def lookup_recording_metadata(
    conn: MusicBrainzDB, mbids: Iterable[str]
) -> dict[str, dict[str, Any]]:
    """
    Lookup MusicBrainz metadata for the specified MBIDs.
    """
    if not mbids:
        return {}
    src = schema.mb_recording.join(schema.mb_artist_credit)
    query = (
        sql.select(
            schema.mb_recording.c.gid,
            schema.mb_recording.c.name,
            schema.mb_recording.c.length,
            schema.mb_recording.c.comment,
            schema.mb_artist_credit.c.name.label("artist_name"),
        )
        .where(schema.mb_recording.c.gid.in_(mbids))
        .select_from(src)
    )
    results = {}
    for row in conn.execute(query):
        result = dict(row._mapping)
        result["length"] = (result["length"] or 0) / 1000
        results[row.gid] = result
    return results


def resolve_mbid_redirect(conn: MusicBrainzDB, mbid: str) -> str:
    src = schema.mb_recording
    src = src.join(
        schema.mb_recording_gid_redirect,
        schema.mb_recording_gid_redirect.c.new_id == schema.mb_recording.c.id,
    )
    condition = schema.mb_recording_gid_redirect.c.gid == mbid
    columns = [schema.mb_recording.c.gid]
    query = sql.select(*columns).where(condition).select_from(src)
    new_mbid = conn.execute(query).scalar()
    return new_mbid or mbid
