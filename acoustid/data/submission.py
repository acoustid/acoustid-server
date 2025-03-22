# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
import logging
import uuid
from typing import Any, Dict, Iterable, List, Optional, Set

import pytz
from sqlalchemy import RowMapping, sql

from acoustid import const
from acoustid import tables as schema
from acoustid.data.fingerprint import (
    FingerprintSearcher,
    inc_fingerprint_submission_count,
    insert_fingerprint,
)
from acoustid.data.foreignid import find_or_insert_foreignid, get_foreignid
from acoustid.data.format import find_or_insert_format
from acoustid.data.meta import check_meta_id, find_or_insert_meta, fix_meta
from acoustid.data.source import find_or_insert_source, get_source
from acoustid.data.track import (
    can_add_fp_to_track,
    can_merge_tracks,
    insert_mbid,
    insert_puid,
    insert_track,
    insert_track_foreignid,
    insert_track_meta,
    merge_tracks,
)
from acoustid.db import AppDB, FingerprintDB, IngestDB, pg_try_advisory_xact_lock
from acoustid.indexclient import IndexClientPool

logger = logging.getLogger(__name__)


def insert_submission(ingest_db, values):
    # type: (IngestDB, Dict[str, Any]) -> int
    """
    Insert a new submission into the database
    """
    values = dict((k, v) for (k, v) in values.items() if v is not None)
    insert_stmt = schema.submission.insert().values(values)
    submission_id = ingest_db.execute(insert_stmt).inserted_primary_key[0]
    logger.debug("Inserted submission %r with data %r", submission_id, values)
    return submission_id


def insert_submission_result(ingest_db, values):
    # type: (IngestDB, Dict[str, Any]) -> int
    """
    Insert a new submission result into the database
    """
    values = dict((k, v) for (k, v) in values.items() if v is not None)
    insert_stmt = schema.submission_result.insert().values(values)
    ingest_db.execute(insert_stmt)
    submission_id = int(values["submission_id"])
    logger.debug("Inserted submission_result %r with data %r", submission_id, values)
    return submission_id


def import_submission(ingest_db, app_db, fingerprint_db, index_pool, submission):
    # type: (IngestDB, AppDB, FingerprintDB, IndexClientPool, RowMapping) -> Optional[Dict[str, Any]]
    """
    Import the given submission into the main fingerprint database
    """

    if not pg_try_advisory_xact_lock(
        ingest_db, "import.fp", str(submission["fingerprint"])
    ):
        logger.info(
            "Skipping import of submission %d because a related submission is being imported (will be retried)",
            submission["id"],
        )
        return None

    if not pg_try_advisory_xact_lock(
        ingest_db, "import.mbid", submission["mbid"] or ""
    ):
        logger.info(
            "Skipping import of submission %d because a related submission is being imported (will be retried)",
            submission["id"],
        )
        return None

    handled_at = datetime.datetime.now(pytz.utc)

    update_stmt = schema.submission.update().where(
        schema.submission.c.id == submission["id"]
    )
    ingest_db.execute(update_stmt.values(handled=True))
    ingest_db.execute(update_stmt.values(handled=True, handled_at=handled_at))
    logger.info(
        "Importing submission %d with MBIDs %s", submission["id"], submission["mbid"]
    )

    has_mbid = (
        submission["mbid"]
        and submission["mbid"] != "00000000-0000-0000-0000-000000000000"
    )
    has_puid = (
        submission["puid"]
        and submission["puid"] != "00000000-0000-0000-0000-000000000000"
    )
    has_meta = submission["meta_id"] or submission["meta"]

    if not has_mbid and not has_puid and not has_meta:
        logger.info("Skipping, missing metadata")
        return None

    num_unique_items = len(set(submission["fingerprint"]))
    if num_unique_items < const.FINGERPRINT_MIN_UNIQUE_ITEMS:
        logger.info("Skipping, has only %d unique items", num_unique_items)
        return None

    num_query_items = fingerprint_db.execute(
        sql.select(
            sql.func.icount(sql.func.acoustid_extract_query(submission["fingerprint"]))
        )
    ).scalar()
    if not num_query_items:
        logger.info("Skipping, no data to index")
        return None

    source_id = submission["source_id"]
    if source_id is not None:
        source = get_source(app_db, source_id)
        if source is None:
            logger.error("Source not found")
            return None
    else:
        source = {
            "application_id": submission["application_id"],
            "version": submission["application_version"],
            "account_id": submission["account_id"],
        }
        source_id = find_or_insert_source(
            app_db, source["application_id"], source["account_id"], source["version"]
        )

    submission_result = {
        "submission_id": submission["id"],
        "created": submission["created"],
        "handled_at": handled_at,
        "account_id": source["account_id"],
        "application_id": source["application_id"],
        "application_version": source["version"],
    }

    format_id = submission["format_id"]
    if format_id is None and submission["format"] is not None:
        format_id = find_or_insert_format(app_db, submission["format"])

    fingerprint = {
        "id": None,
        "track_id": None,
        "fingerprint": submission["fingerprint"],
        "length": submission["length"],
        "bitrate": submission["bitrate"],
        "format_id": format_id,
    }

    searcher = FingerprintSearcher(fingerprint_db, index_pool, fast=False)
    searcher.min_score = const.TRACK_MERGE_THRESHOLD
    matches = searcher.search(submission["fingerprint"], submission["length"])
    if matches:
        all_track_ids = set()  # type: Set[int]
        possible_track_ids = set()  # type: Set[int]
        for m in matches:
            if m.track_id in all_track_ids:
                continue
            all_track_ids.add(m.track_id)
            logger.debug(
                "Fingerprint %d with track %d is %d%% similar",
                m.fingerprint_id,
                m.track_id,
                m.score * 100,
            )
            if can_add_fp_to_track(
                fingerprint_db,
                m.track_id,
                submission["fingerprint"],
                submission["length"],
            ):
                possible_track_ids.add(m.track_id)
                if not fingerprint["track_id"]:
                    fingerprint["track_id"] = m.track_id
                    if m.score > const.FINGERPRINT_MERGE_THRESHOLD:
                        fingerprint["id"] = m.fingerprint_id
        # TODO fix merge_tracks to not delete track_mbid rows and then enable it
        if len(possible_track_ids) > 1 and False:
            for group in can_merge_tracks(fingerprint_db, possible_track_ids):
                if fingerprint["track_id"] in group and len(group) > 1:
                    fingerprint["track_id"] = min(group)
                    group.remove(fingerprint["track_id"])
                    merge_tracks(
                        fingerprint_db, ingest_db, fingerprint["track_id"], list(group)
                    )
                    break

    if not fingerprint["track_id"]:
        fingerprint["track_id"] = insert_track(fingerprint_db)

    assert isinstance(fingerprint["track_id"], int)
    submission_result["track_id"] = fingerprint["track_id"]

    if not fingerprint["id"]:
        fingerprint["id"] = insert_fingerprint(
            fingerprint_db, ingest_db, fingerprint, submission["id"], source_id
        )
    else:
        assert isinstance(fingerprint["id"], int)
        inc_fingerprint_submission_count(
            fingerprint_db, ingest_db, fingerprint["id"], submission["id"], source_id
        )

    submission_result["fingerprint_id"] = fingerprint["id"]

    if has_mbid:
        insert_mbid(
            fingerprint_db,
            ingest_db,
            fingerprint["track_id"],
            submission["mbid"],
            submission["id"],
            source_id,
        )
        submission_result["mbid"] = submission["mbid"]

    if has_puid:
        insert_puid(
            fingerprint_db,
            ingest_db,
            fingerprint["track_id"],
            submission["puid"],
            submission["id"],
            source_id,
        )
        submission_result["puid"] = submission["puid"]

    if has_meta:
        meta_id = submission["meta_id"]  # type: Optional[int]
        meta_gid = None  # type: Optional[uuid.UUID]
        if meta_id is None:
            meta = fix_meta(submission["meta"])
            meta_id, meta_gid = find_or_insert_meta(fingerprint_db, meta)
        else:
            found, meta_gid = check_meta_id(fingerprint_db, meta_id)
            if not found:
                logger.error("Meta not found")
                meta_id = None
        if meta_id is not None:
            insert_track_meta(
                fingerprint_db,
                ingest_db,
                fingerprint["track_id"],
                meta_id,
                submission["id"],
                source_id,
            )
            submission_result["meta_id"] = meta_id
            submission_result["meta_gid"] = meta_gid

    if submission["foreignid_id"] or submission["foreignid"]:
        foreignid_id = submission["foreignid_id"]
        if foreignid_id is None:
            foreignid = submission["foreignid"]
            foreignid_id = find_or_insert_foreignid(fingerprint_db, foreignid)
        else:
            foreignid = get_foreignid(fingerprint_db, foreignid_id)
        insert_track_foreignid(
            fingerprint_db,
            ingest_db,
            fingerprint["track_id"],
            foreignid_id,
            submission["id"],
            source_id,
        )
        submission_result["foreignid"] = foreignid

    insert_submission_result(ingest_db, submission_result)

    return fingerprint


def import_queued_submissions(
    ingest_db, app_db, fingerprint_db, index, limit=100, ids=None
):
    # type: (IngestDB, AppDB, FingerprintDB, IndexClientPool, int, Optional[List[int]]) -> int
    """
    Import the given submission into the main fingerprint database
    """
    query = (
        schema.submission.select()
        .where(schema.submission.c.handled.is_(False))
        .with_for_update(skip_locked=True)
    )
    if ids is not None:
        query = query.where(schema.submission.c.id.in_(ids))
    if limit is not None:
        query = query.limit(limit)
    count = 0
    for submission in ingest_db.execute(query):
        result = import_submission(
            ingest_db, app_db, fingerprint_db, index, submission._mapping
        )
        if result is not None:
            count += 1
    return count


def lookup_submission_status(
    ingest_db: IngestDB, fingerprint_db: FingerprintDB, ids: Iterable[int]
) -> Dict[int, str]:
    if not ids:
        return {}

    query = sql.select(
        schema.fingerprint_source.c.submission_id,
        schema.fingerprint_source.c.fingerprint_id,
    ).where(schema.fingerprint_source.c.submission_id.in_(ids))
    fingerprint_ids: Dict[int, int] = {}
    for submission_id, fingerprint_id in ingest_db.execute(query):
        fingerprint_ids[submission_id] = fingerprint_id

    if not fingerprint_ids:
        return {}

    source = schema.fingerprint.join(schema.track)
    query = (
        sql.select(
            schema.fingerprint.c.id,
            schema.track.c.gid,
        )
        .select_from(source)
        .where(schema.fingerprint.c.id.in_(fingerprint_ids.values()))
    )
    track_gids: Dict[int, str] = {}
    for fingerprint_id, track_gid in fingerprint_db.execute(query):
        track_gids[fingerprint_id] = track_gid

    if not track_gids:
        return {}

    results: Dict[int, str] = {}
    for submission_id in ids:
        fingerprint_id = fingerprint_ids.get(submission_id)
        if fingerprint_id is not None:
            track_gid = track_gids.get(fingerprint_id)
            if track_gid is not None:
                results[submission_id] = track_gid

    return results
