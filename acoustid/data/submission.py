# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
import datetime
import uuid
import pytz
from typing import Dict, Any, Optional, Set, List, Iterable
from sqlalchemy import sql
from acoustid import tables as schema, const
from acoustid.data.fingerprint import insert_fingerprint, inc_fingerprint_submission_count, FingerprintSearcher
from acoustid.data.meta import fix_meta, find_or_insert_meta
from acoustid.data.track import (
    insert_track, insert_mbid, insert_puid, merge_tracks, insert_track_meta,
    can_add_fp_to_track, can_merge_tracks, insert_track_foreignid,
)
from acoustid.db import FingerprintDB, IngestDB, AppDB
from acoustid.indexclient import IndexClientPool
from acoustid.data.meta import check_meta_id
from acoustid.data.format import find_or_insert_format
from acoustid.data.source import get_source, find_or_insert_source
from acoustid.data.foreignid import get_foreignid, find_or_insert_foreignid

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
    submission_id = int(values['submission_id'])
    logger.debug("Inserted submission_result %r with data %r", submission_id, values)
    return submission_id


def import_submission(ingest_db, app_db, fingerprint_db, index_pool, submission):
    # type: (IngestDB, AppDB, FingerprintDB, IndexClientPool, Dict[str, Any]) -> Optional[Dict[str, Any]]
    """
    Import the given submission into the main fingerprint database
    """

    handled_at = datetime.datetime.now(pytz.utc)

    update_stmt = schema.submission.update().where(
        schema.submission.c.id == submission['id'])
    ingest_db.execute(update_stmt.values(handled=True))
    ingest_db.execute(update_stmt.values(handled=True, handled_at=handled_at))
    logger.info("Importing submission %d with MBIDs %s", submission['id'], submission['mbid'])

    num_unique_items = len(set(submission['fingerprint']))
    if num_unique_items < const.FINGERPRINT_MIN_UNIQUE_ITEMS:
        logger.info("Skipping, has only %d unique items", num_unique_items)
        return None

    num_query_items = fingerprint_db.execute("SELECT icount(acoustid_extract_query(%(fp)s))", dict(fp=submission['fingerprint']))
    if not num_query_items:
        logger.info("Skipping, no data to index")
        return None

    source_id = submission['source_id']
    if source_id is not None:
        source = get_source(app_db, source_id)
        if source is None:
            logger.error("Source not found")
            return None
    else:
        source = {
            'application_id': submission['application_id'],
            'version': submission['application_version'],
            'account_id': submission['account_id'],
        }
        source_id = find_or_insert_source(app_db, source['application_id'], source['account_id'], source['version'])

    submission_result = {
        'submission_id': submission['id'],
        'created': submission['created'],
        'handled_at': handled_at,
        'account_id': source['account_id'],
        'application_id': source['application_id'],
        'application_version': source['version'],
    }

    format_id = submission['format_id']
    if format_id is None and submission['format'] is not None:
        format_id = find_or_insert_format(app_db, submission['format'])

    fingerprint = {
        'id': None,
        'track_id': None,
        'fingerprint': submission['fingerprint'],
        'length': submission['length'],
        'bitrate': submission['bitrate'],
        'format_id': format_id,
    }

    searcher = FingerprintSearcher(fingerprint_db, index_pool, fast=False)
    searcher.min_score = const.TRACK_MERGE_THRESHOLD
    matches = searcher.search(submission['fingerprint'], submission['length'])
    if matches:
        all_track_ids = set()  # type: Set[int]
        possible_track_ids = set()  # type: Set[int]
        for m in matches:
            if m.track_id in all_track_ids:
                continue
            all_track_ids.add(m.track_id)
            logger.debug("Fingerprint %d with track %d is %d%% similar", m.fingerprint_id, m.track_id, m.score * 100)
            if can_add_fp_to_track(fingerprint_db, m.track_id, submission['fingerprint'], submission['length']):
                possible_track_ids.add(m.track_id)
                if not fingerprint['track_id']:
                    fingerprint['track_id'] = m.track_id
                    if m.score > const.FINGERPRINT_MERGE_THRESHOLD:
                        fingerprint['id'] = m.fingerprint_id
        if len(possible_track_ids) > 1:
            for group in can_merge_tracks(fingerprint_db, possible_track_ids):
                if fingerprint['track_id'] in group and len(group) > 1:
                    fingerprint['track_id'] = min(group)
                    group.remove(fingerprint['track_id'])
                    merge_tracks(fingerprint_db, ingest_db, fingerprint['track_id'], list(group))
                    break

    if not fingerprint['track_id']:
        fingerprint['track_id'] = insert_track(fingerprint_db)

    assert isinstance(fingerprint['track_id'], int)
    submission_result['track_id'] = fingerprint['track_id']

    if not fingerprint['id']:
        fingerprint['id'] = insert_fingerprint(fingerprint_db, ingest_db, fingerprint, submission['id'], source_id)
    else:
        assert isinstance(fingerprint['id'], int)
        inc_fingerprint_submission_count(fingerprint_db, ingest_db, fingerprint['id'], submission['id'], source_id)

    submission_result['fingerprint_id'] = fingerprint['id']

    if submission['mbid'] and submission['mbid'] != '00000000-0000-0000-0000-000000000000':
        insert_mbid(fingerprint_db, ingest_db, fingerprint['track_id'], submission['mbid'], submission['id'], source_id)
        submission_result['mbid'] = submission['mbid']

    if submission['puid'] and submission['puid'] != '00000000-0000-0000-0000-000000000000':
        insert_puid(fingerprint_db, ingest_db, fingerprint['track_id'], submission['puid'], submission['id'], source_id)
        submission_result['puid'] = submission['puid']

    if submission['meta_id'] or submission['meta']:
        meta_id = submission['meta_id']  # type: Optional[int]
        meta_gid = None  # type: Optional[uuid.UUID]
        if meta_id is None:
            meta = fix_meta(submission['meta'])
            meta_id, meta_gid = find_or_insert_meta(fingerprint_db, meta)
        else:
            found, meta_gid = check_meta_id(fingerprint_db, meta_id)
            if not found:
                logger.error("Meta not found")
                meta_id = None
        if meta_id is not None:
            insert_track_meta(fingerprint_db, ingest_db, fingerprint['track_id'], meta_id, submission['id'], source_id)
            submission_result['meta_id'] = meta_id
            submission_result['meta_gid'] = meta_gid

    if submission['foreignid_id'] or submission['foreignid']:
        foreignid_id = submission['foreignid_id']
        if foreignid_id is None:
            foreignid = submission['foreignid']
            foreignid_id = find_or_insert_foreignid(fingerprint_db, foreignid)
        else:
            foreignid = get_foreignid(fingerprint_db, foreignid_id)
        insert_track_foreignid(fingerprint_db, ingest_db, fingerprint['track_id'], foreignid_id, submission['id'], source_id)
        submission_result['foreignid'] = foreignid

    insert_submission_result(ingest_db, submission_result)

    return fingerprint


def import_queued_submissions(ingest_db, app_db, fingerprint_db, index, limit=100, ids=None):
    # type: (IngestDB, AppDB, FingerprintDB, IndexClientPool, int, Optional[List[int]]) -> int
    """
    Import the given submission into the main fingerprint database
    """
    query = (
        schema.submission.select(schema.submission.c.handled.is_(False))
        .with_for_update(skip_locked=True)
    )
    if ids is not None:
        query = query.where(schema.submission.c.id.in_(ids))
    if limit is not None:
        query = query.limit(limit)
    count = 0
    for submission in ingest_db.execute(query):
        import_submission(ingest_db, app_db, fingerprint_db, index, submission)
        count += 1
    return count


def lookup_submission_status(ingest_db, fingerprint_db, ids):
    # type: (IngestDB, FingerprintDB, Iterable[int]) -> Dict[int, str]
    if not ids:
        return {}

    query = sql.select([schema.fingerprint_source.c.submission_id, schema.fingerprint_source.c.fingerprint_id]).\
        where(schema.fingerprint_source.c.submission_id.in_(ids))
    fingerprint_ids = {}  # type: Dict[int, int]
    for submission_id, fingerprint_id in ingest_db.execute(query):
        fingerprint_ids[submission_id] = fingerprint_id

    if not fingerprint_ids:
        return {}

    source = schema.fingerprint.join(schema.track)
    query = sql.select([schema.fingerprint.c.id, schema.track.c.gid], from_obj=source).\
        where(schema.fingerprint.c.id.in_(fingerprint_ids))
    track_gids = {}  # type: Dict[int, str]
    for fingerprint_id, track_gid in fingerprint_db.execute(query):
        track_gids[fingerprint_id] = track_gid

    if not track_gids:
        return {}

    results = {}  # type: Dict[int, str]
    for submission_id in ids:
        fingerprint_id = fingerprint_ids[submission_id]
        track_gid = track_gids[fingerprint_id]
        results[submission_id] = track_gid

    return results
