# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
import uuid
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union
from uuid import UUID

from sqlalchemy import Column, Row, Table, sql

from acoustid import const
from acoustid import tables as schema
from acoustid.db import FingerprintDB, IngestDB, MusicBrainzDB, pg_advisory_xact_lock

logger = logging.getLogger(__name__)


def resolve_track_gid(conn: FingerprintDB, gid: str) -> int | None:
    query = sql.select(schema.track.c.id, schema.track.c.new_id).where(
        schema.track.c.gid == gid
    )
    row = conn.execute(query).first()
    if row is None:
        return None
    track_id, new_track_id = row
    if new_track_id is None:
        return track_id
    query = sql.select(schema.track.c.id).where(schema.track.c.id == new_track_id)
    return conn.execute(query).scalar()


def lookup_mbids(conn, track_ids):
    # type: (FingerprintDB, Iterable[int]) -> Dict[int, List[Tuple[str, int]]]
    """
    Lookup MBIDs for the specified AcoustID track IDs.
    """
    if not track_ids:
        return {}
    query = sql.select(
        schema.track_mbid.c.track_id,
        schema.track_mbid.c.mbid,
        schema.track_mbid.c.submission_count,
    )
    query = query.where(
        sql.and_(
            schema.track_mbid.c.track_id.in_(track_ids),
            schema.track_mbid.c.disabled.is_(False),
        )
    )
    query = query.order_by(schema.track_mbid.c.mbid)
    results = {}  # type: Dict[int, List[Tuple[str, int]]]
    for track_id, mbid, sources in conn.execute(query):
        results.setdefault(track_id, []).append((mbid, sources))
    return results


def lookup_meta_ids(conn, track_ids, max_ids_per_track=None):
    # type: (FingerprintDB, Iterable[int], Optional[int]) -> Dict[int, List[int]]
    if not track_ids:
        return {}
    query = (
        sql.select(schema.track_meta.c.track_id, schema.track_meta.c.meta_id)
        .where(
            sql.and_(schema.track_meta.c.track_id.in_(track_ids)),
        )
        .order_by(
            schema.track_meta.c.track_id, schema.track_meta.c.submission_count.desc()
        )
    )
    results = {}  # type: Dict[int, List[int]]
    for track_id, meta_id in conn.execute(query):
        track_meta_ids = results.setdefault(track_id, [])
        if max_ids_per_track is not None and len(track_meta_ids) >= max_ids_per_track:
            continue
        track_meta_ids.append(meta_id)
    return results


def lookup_tracks(conn, mbids):
    # type: (FingerprintDB, Iterable[int]) -> Dict[str, List[Dict[str, Any]]]
    if not mbids:
        return {}
    query = (
        sql.select(
            schema.track_mbid.c.track_id, schema.track.c.gid, schema.track_mbid.c.mbid
        )
        .where(
            sql.and_(
                schema.track_mbid.c.mbid.in_(mbids),
                schema.track_mbid.c.disabled.is_(False),
                schema.track_mbid.c.track_id == schema.track.c.id,
            ),
        )
        .order_by(schema.track_mbid.c.track_id)
    )
    results = {}  # type: Dict[str, List[Dict[str, Any]]]
    for track_id, track_gid, mbid in conn.execute(query):
        results.setdefault(mbid, []).append({"id": track_id, "gid": track_gid})
    return results


def disable_mbid(
    fingerprint_db: FingerprintDB,
    ingest_db: IngestDB,
    mbid: str,
    account_id: int,
    note: str,
) -> None:
    result = fingerprint_db.execute(
        schema.track_mbid.update()
        .returning(schema.track_mbid.c.id)
        .where(schema.track_mbid.c.mbid == mbid)
        .values(
            disabled=True,
            updated=sql.func.current_timestamp(),
        )
    )
    for row in result:
        ingest_db.execute(
            schema.track_mbid_change.insert().values(
                track_mbid_id=row.id,
                updated=sql.func.current_timestamp(),
                note=note,
                account_id=account_id,
                disabled=True,
            )
        )


def merge_mbids(
    fingerprint_db: FingerprintDB,
    ingest_db: IngestDB,
    source_mbid: UUID,
    target_mbid: UUID,
) -> None:
    pg_advisory_xact_lock(fingerprint_db, "merge_mbids:target", str(target_mbid))

    logger.info("Merging MBID %r into %r", source_mbid, target_mbid)
    affected_track_mbids_queries = []
    for mbid in [target_mbid, source_mbid]:
        affected_track_mbids_queries.append(
            sql.select(
                schema.track_mbid.c.id,
                schema.track_mbid.c.track_id,
                schema.track_mbid.c.mbid,
                schema.track_mbid.c.submission_count,
                schema.track_mbid.c.disabled,
                schema.track_mbid.c.merged_into,
            )
            .where(schema.track_mbid.c.mbid == mbid)
            .with_for_update()
        )

    track_mbids_by_track_id: dict[int, dict[UUID, Any]] = {}
    for query in affected_track_mbids_queries:
        for row in fingerprint_db.execute(query):
            track_mbids_by_track_id.setdefault(row.track_id, {})[row.mbid] = row

    for track_id, track_mbids in track_mbids_by_track_id.items():
        source = track_mbids.get(source_mbid)
        if source is None:
            # source mbid not found, skip this track
            continue

        target = track_mbids.get(target_mbid)
        if target is None:
            # we have no record with the target mbid, so we create a new one
            target_id = fingerprint_db.execute(
                schema.track_mbid.insert()
                .returning(schema.track_mbid.c.id)
                .values(
                    track_id=track_id,
                    mbid=target_mbid,
                    submission_count=0,
                    disabled=False,
                )
            ).scalar()
        else:
            # we already have a record with the target mbid, so we update it
            target_id = target.id

        if source.merged_into is not None and source.merged_into != target_id:
            raise ValueError("source mbid is already merged into another mbid")

        # clear submission count and disable flag for source mbid
        fingerprint_db.execute(
            schema.track_mbid.update()
            .where(schema.track_mbid.c.id == source.id)
            .values(
                merged_into=target_id,
                submission_count=0,
                disabled=True,
                updated=sql.func.current_timestamp(),
            )
        )

        # update submission count and disable flag for target mbid
        fingerprint_db.execute(
            schema.track_mbid.update()
            .where(schema.track_mbid.c.id == target_id)
            .values(
                submission_count=(
                    schema.track_mbid.c.submission_count + source.submission_count
                ),
                disabled=sql.and_(
                    schema.track_mbid.c.disabled,
                    source.disabled,
                ),
                updated=sql.func.current_timestamp(),
            )
        )

        # update track_mbid_source and track_mbid_change tables
        ingest_db.execute(
            schema.track_mbid_source.update()
            .where(schema.track_mbid_source.c.track_mbid_id == source.id)
            .values(
                track_mbid_id=target_id,
                updated=sql.func.current_timestamp(),
            )
        )
        ingest_db.execute(
            schema.track_mbid_change.update()
            .where(schema.track_mbid_change.c.track_mbid_id == source.id)
            .values(
                track_mbid_id=target_id,
                updated=sql.func.current_timestamp(),
            )
        )


def merge_missing_mbid(
    fingerprint_db: FingerprintDB,
    ingest_db: IngestDB,
    musicbrainz_db: MusicBrainzDB,
    old_mbid: UUID,
) -> bool:
    """
    Lookup which MBIDs has been merged in MusicBrainz and merge then
    in the AcoustID database as well.
    """

    new_mbid = musicbrainz_db.execute(
        sql.select(schema.mb_recording.c.gid)
        .where(schema.mb_recording.c.id == schema.mb_recording_gid_redirect.c.new_id)
        .where(schema.mb_recording_gid_redirect.c.gid == old_mbid)
    ).scalar_one_or_none()
    if new_mbid is not None:
        merge_mbids(fingerprint_db, ingest_db, old_mbid, new_mbid)
        return True

    new_mbid = musicbrainz_db.execute(
        sql.select(schema.mb_recording.c.gid).where(
            schema.mb_recording.c.gid == old_mbid
        )
    ).scalar()
    if new_mbid:
        return True

    logger.debug("MBID %r not found in MusicBrainz", old_mbid)
    return False


def _merge_tracks_gids(fingerprint_db, ingest_db, name_with_id, target_id, source_ids):
    name = name_with_id.replace("_id", "")
    tab = schema.metadata.tables["track_%s" % name]
    col = tab.columns[name_with_id]
    tab_src = schema.metadata.tables["track_%s_source" % name]
    col_src = tab_src.columns["track_%s_id" % name]
    if name == "mbid":
        tab_chg = schema.metadata.tables["track_%s_change" % name]
        col_chg = tab_chg.columns["track_%s_id" % name]
    columns = [
        sql.func.min(tab.c.id).label("id"),
        sql.func.array_agg(tab.c.id).label("all_ids"),
        sql.func.sum(tab.c.submission_count).label("count"),
    ]
    if name == "mbid":
        columns.append(
            sql.func.every(schema.track_mbid.c.disabled).label("all_disabled")
        )
    query = (
        sql.select(*columns)
        .where(tab.c.track_id.in_(source_ids + [target_id]))
        .group_by(col)
    )
    rows = fingerprint_db.execute(query).fetchall()
    to_delete = set()
    to_update = []
    for row in rows:
        old_ids = set(row.all_ids)
        old_ids.remove(row.id)
        to_delete.update(old_ids)
        to_update.append((old_ids, row))
        if old_ids:
            update_stmt = tab_src.update().where(col_src.in_(old_ids))
            ingest_db.execute(update_stmt.values({col_src: row.id}))
            if name == "mbid":
                update_stmt = tab_chg.update().where(col_chg.in_(old_ids))
                ingest_db.execute(update_stmt.values({col_chg: row.id}))
    if to_delete:
        delete_stmt = tab.delete().where(tab.c.id.in_(to_delete))
        fingerprint_db.execute(delete_stmt)
    for old_ids, row in to_update:
        update_stmt = tab.update().where(tab.c.id == row.id)
        if name == "mbid":
            fingerprint_db.execute(
                update_stmt.values(
                    submission_count=row.count,
                    track_id=target_id,
                    disabled=row.all_disabled,
                    updated=sql.func.current_timestamp(),
                )
            )
        else:
            fingerprint_db.execute(
                update_stmt.values(
                    submission_count=row.count,
                    track_id=target_id,
                    updated=sql.func.current_timestamp(),
                )
            )


def merge_tracks(fingerprint_db, ingest_db, target_id, source_ids):
    # type: (FingerprintDB, IngestDB, int, List[int]) -> None
    """
    Merge the specified tracks.
    """
    logger.info("Merging tracks %s into %s", ", ".join(map(str, source_ids)), target_id)
    _merge_tracks_gids(fingerprint_db, ingest_db, "mbid", target_id, source_ids)
    _merge_tracks_gids(fingerprint_db, ingest_db, "puid", target_id, source_ids)
    _merge_tracks_gids(fingerprint_db, ingest_db, "meta_id", target_id, source_ids)
    _merge_tracks_gids(fingerprint_db, ingest_db, "foreignid_id", target_id, source_ids)
    # XXX don't move duplicate fingerprints
    update_stmt = schema.fingerprint.update().where(
        schema.fingerprint.c.track_id.in_(source_ids)
    )
    fingerprint_db.execute(
        update_stmt.values(
            track_id=target_id,
            updated=sql.func.current_timestamp(),
        )
    )
    update_stmt = schema.track.update().where(
        sql.or_(
            schema.track.c.id.in_(source_ids), schema.track.c.new_id.in_(source_ids)
        )
    )
    fingerprint_db.execute(
        update_stmt.values(
            new_id=target_id,
            updated=sql.func.current_timestamp(),
        )
    )


def insert_track(conn):
    """
    Insert a new track into the database
    """
    insert_stmt = schema.track.insert().values({"gid": str(uuid.uuid4())})
    id = conn.execute(insert_stmt).inserted_primary_key[0]
    logger.debug("Inserted track %r", id)
    return id


def _insert_gid(
    fingerprint_db,
    ingest_db,
    tab,
    tab_src,
    col,
    name,
    track_id,
    gid,
    submission_id=None,
    source_id=None,
):
    # type: (FingerprintDB, IngestDB, Table, Table, Column, str, int, Union[str, int], Optional[int], Optional[int]) -> None
    cond = sql.and_(tab.c.track_id == track_id, col == gid)
    query = sql.select(tab.c.id).where(cond)
    id = fingerprint_db.execute(query).scalar()
    if id is not None:
        update_stmt = tab.update().where(cond)
        values = {"submission_count": sql.text("submission_count+1")}
        fingerprint_db.execute(update_stmt.values(**values))
    else:
        insert_stmt = tab.insert().values(
            {"track_id": track_id, name: gid, "submission_count": 1}
        )
        id = fingerprint_db.execute(insert_stmt).inserted_primary_key[0]
        logger.debug("Added %s %s to track %d", name.upper(), gid, track_id)
    insert_stmt = tab_src.insert().values(
        {
            "track_%s_id" % name.replace("_id", ""): id,
            "submission_id": submission_id,
            "source_id": source_id,
        }
    )
    ingest_db.execute(insert_stmt)


def insert_mbid(
    fingerprint_db, ingest_db, track_id, mbid, submission_id=None, source_id=None
):
    # type: (FingerprintDB, IngestDB, int, str, Optional[int], Optional[int]) -> None
    _insert_gid(
        fingerprint_db,
        ingest_db,
        schema.track_mbid,
        schema.track_mbid_source,
        schema.track_mbid.c.mbid,
        "mbid",
        track_id,
        mbid,
        submission_id,
        source_id,
    )


def insert_puid(
    fingerprint_db, ingest_db, track_id, puid, submission_id=None, source_id=None
):
    # type: (FingerprintDB, IngestDB, int, str, Optional[int], Optional[int]) -> None
    _insert_gid(
        fingerprint_db,
        ingest_db,
        schema.track_puid,
        schema.track_puid_source,
        schema.track_puid.c.puid,
        "puid",
        track_id,
        puid,
        submission_id,
        source_id,
    )


def insert_track_foreignid(
    fingerprint_db,
    ingest_db,
    track_id,
    foreignid_id,
    submission_id=None,
    source_id=None,
):
    # type: (FingerprintDB, IngestDB, int, int, Optional[int], Optional[int]) -> None
    _insert_gid(
        fingerprint_db,
        ingest_db,
        schema.track_foreignid,
        schema.track_foreignid_source,
        schema.track_foreignid.c.foreignid_id,
        "foreignid_id",
        track_id,
        foreignid_id,
        submission_id,
        source_id,
    )


def insert_track_meta(
    fingerprint_db, ingest_db, track_id, meta_id, submission_id=None, source_id=None
):
    # type: (FingerprintDB, IngestDB, int, int, Optional[int], Optional[int]) -> None
    _insert_gid(
        fingerprint_db,
        ingest_db,
        schema.track_meta,
        schema.track_meta_source,
        schema.track_meta.c.meta_id,
        "meta_id",
        track_id,
        meta_id,
        submission_id,
        source_id,
    )


def calculate_fingerprint_similarity_matrix(conn, track_ids):
    # type: (FingerprintDB, List[int]) -> Dict[int, Dict[int, float]]
    fp1 = schema.fingerprint.alias("fp1")
    fp2 = schema.fingerprint.alias("fp2")
    src = fp1.join(fp2, fp1.c.id < fp2.c.id)
    cond = sql.and_(fp1.c.track_id.in_(track_ids), fp2.c.track_id.in_(track_ids))
    query = (
        sql.select(
            fp1.c.id,
            fp2.c.id,
            sql.func.acoustid_compare2(
                fp1.c.fingerprint, fp2.c.fingerprint, const.TRACK_MAX_OFFSET
            ),
        )
        .where(cond)
        .select_from(src)
        .order_by(fp1.c.id, fp2.c.id)
    )
    result = {}  # type: Dict[int, Dict[int, float]]
    for fp1_id, fp2_id, score in conn.execute(query):
        result.setdefault(fp1_id, {})[fp2_id] = score
        result.setdefault(fp2_id, {})[fp1_id] = score
        result.setdefault(fp1_id, {})[fp1_id] = 1.0
        result.setdefault(fp2_id, {})[fp2_id] = 1.0
    return result


def can_merge_tracks(conn, track_ids):
    # type: (FingerprintDB, Iterable[int]) -> List[Set[int]]
    fp1 = schema.fingerprint.alias("fp1")
    fp2 = schema.fingerprint.alias("fp2")
    join_cond = sql.and_(fp1.c.id < fp2.c.id, fp1.c.track_id < fp2.c.track_id)
    src = fp1.join(fp2, join_cond)
    cond = sql.and_(fp1.c.track_id.in_(track_ids), fp2.c.track_id.in_(track_ids))
    query = (
        sql.select(
            fp1.c.track_id,
            fp2.c.track_id,
            sql.func.max(sql.func.abs(fp1.c.length - fp2.c.length)),
            sql.func.min(
                sql.func.acoustid_compare2(
                    fp1.c.fingerprint, fp2.c.fingerprint, const.TRACK_MAX_OFFSET
                )
            ),
        )
        .where(cond)
        .select_from(src)
        .group_by(fp1.c.track_id, fp2.c.track_id)
        .order_by(fp1.c.track_id, fp2.c.track_id)
    )
    rows = conn.execute(query)
    merges = {}  # type: Dict[int, int]
    for fp1_id, fp2_id, length_diff, score in rows:
        if score < const.TRACK_GROUP_MERGE_THRESHOLD:
            continue
        if length_diff > const.FINGERPRINT_MAX_LENGTH_DIFF:
            continue
        group = fp1_id
        if group in merges:
            group = merges[group]
        merges[fp2_id] = group
    result = []  # type: List[Set[int]]
    for group in set(merges.values()):
        result.append(set([group] + [i for i in merges if merges[i] == group]))
    return result


def can_add_fp_to_track(conn, track_id, fingerprint, length):
    # type: (FingerprintDB, int, List[int], int) -> bool
    query = sql.select(
        sql.func.acoustid_compare2(
            schema.fingerprint.c.fingerprint, fingerprint, const.TRACK_MAX_OFFSET
        ),
        schema.fingerprint.c.length,
    ).where(schema.fingerprint.c.track_id == track_id)
    for fp_score, fp_length in conn.execute(query):
        if fp_score < const.TRACK_GROUP_MERGE_THRESHOLD:
            return False
        if abs(fp_length - length) > const.FINGERPRINT_MAX_LENGTH_DIFF:
            return False
    return True
