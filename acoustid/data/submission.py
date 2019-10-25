# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from typing import Dict, Any, Optional, Set, List, Iterable
from sqlalchemy import sql
from acoustid import tables as schema, const
from acoustid.data.fingerprint import insert_fingerprint, inc_fingerprint_submission_count, FingerprintSearcher
from acoustid.data.track import (
    insert_track, insert_mbid, insert_puid, merge_tracks, insert_track_meta,
    can_add_fp_to_track, can_merge_tracks, insert_track_foreignid,
)
from acoustid.db import FingerprintDB, IngestDB, AppDB
from acoustid.indexclient import IndexClientPool
from acoustid.data.source import get_source
from acoustid.data.foreignid import get_foreignid

logger = logging.getLogger(__name__)


def insert_submission(ingest_db, data):
    # type: (IngestDB, Dict[str, Any]) -> int
    """
    Insert a new submission into the database
    """
    insert_stmt = schema.submission.insert().values({
        'fingerprint': data['fingerprint'],
        'length': data['length'],
        'bitrate': data.get('bitrate'),
        'mbid': data.get('mbid'),
        'puid': data.get('puid'),
        'source_id': data.get('source_id'),
        'format_id': data.get('format_id'),
        'meta_id': data.get('meta_id'),
        'foreignid_id': data.get('foreignid_id'),
    })
    submission_id = ingest_db.execute(insert_stmt).inserted_primary_key[0]
    logger.debug("Inserted submission %r with data %r", submission_id, data)
    return submission_id


def insert_submission_result(ingest_db, data):
    # type: (IngestDB, Dict[str, Any]) -> None
    """
    Insert a new submission result into the database
    """
    insert_stmt = schema.submission_result.insert().values({
        'submission_id': data['submission_id'],
        'created': data['created'],
        'account_id': data['account_id'],
        'application_id': data['application_id'],
        'application_version': data.get('application_version'),
        'fingerprint_id': data['fingerprint_id'],
        'track_id': data['track_id'],
        'mbid': data.get('mbid'),
        'puid': data.get('puid'),
        'meta_id': data.get('meta_id'),
        'foreignid': data.get('foreignid'),
    })
    ingest_db.execute(insert_stmt)


def import_submission(ingest_db, app_db, fingerprint_db, index_pool, submission):
    # type: (IngestDB, AppDB, FingerprintDB, IndexClientPool, Dict[str, Any]) -> Optional[Dict[str, Any]]
    """
    Import the given submission into the main fingerprint database
    """
    update_stmt = schema.submission.update().where(
        schema.submission.c.id == submission['id'])
    ingest_db.execute(update_stmt.values(handled=True))
    logger.info("Importing submission %d with MBIDs %s", submission['id'], submission['mbid'])

    num_unique_items = len(set(submission['fingerprint']))
    if num_unique_items < const.FINGERPRINT_MIN_UNIQUE_ITEMS:
        logger.info("Skipping, has only %d unique items", num_unique_items)
        return None

    num_query_items = fingerprint_db.execute("SELECT icount(acoustid_extract_query(%(fp)s))", dict(fp=submission['fingerprint']))
    if not num_query_items:
        logger.info("Skipping, no data to index")
        return None

    source = get_source(app_db, submission['source_id'])
    if source is None:
        logger.error("Source not found")
        return None

    submission_result = {
        'submission_id': submission['id'],
        'created': submission['created'],
        'account_id': source['account_id'],
        'application_id': source['application_id'],
        'application_version': source['version'],
    }

    fingerprint = {
        'id': None,
        'track_id': None,
        'fingerprint': submission['fingerprint'],
        'length': submission['length'],
        'bitrate': submission['bitrate'],
        'format_id': submission['format_id'],
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
                    merge_tracks(fingerprint_db, fingerprint['track_id'], list(group))
                    break

    if not fingerprint['track_id']:
        fingerprint['track_id'] = insert_track(fingerprint_db)

    assert isinstance(fingerprint['track_id'], int)
    submission_result['track_id'] = fingerprint['track_id']

    if not fingerprint['id']:
        fingerprint['id'] = insert_fingerprint(fingerprint_db, ingest_db, fingerprint, submission['id'], submission['source_id'])
    else:
        assert isinstance(fingerprint['id'], int)
        inc_fingerprint_submission_count(fingerprint_db, ingest_db, fingerprint['id'], submission['id'], submission['source_id'])

    submission_result['fingerprint_id'] = fingerprint['id']

    if submission['mbid'] and submission['mbid'] != '00000000-0000-0000-0000-000000000000':
        insert_mbid(fingerprint_db, ingest_db, fingerprint['track_id'], submission['mbid'], submission['id'], submission['source_id'])
        submission_result['mbid'] = submission['mbid']

    if submission['puid'] and submission['puid'] != '00000000-0000-0000-0000-000000000000':
        insert_puid(fingerprint_db, ingest_db, fingerprint['track_id'], submission['puid'], submission['id'], submission['source_id'])
        submission_result['puid'] = submission['puid']

    if submission['meta_id']:
        insert_track_meta(fingerprint_db, ingest_db, fingerprint['track_id'], submission['meta_id'], submission['id'], submission['source_id'])
        submission_result['meta_id'] = submission['meta_id']

    if submission['foreignid_id']:
        insert_track_foreignid(fingerprint_db, ingest_db, fingerprint['track_id'], submission['foreignid_id'], submission['id'], submission['source_id'])
        submission_result['foreignid'] = get_foreignid(fingerprint_db, submission['foreignid_id'])

    insert_submission_result(ingest_db, submission_result)

    return fingerprint


def import_queued_submissions(ingest_db, app_db, fingerprint_db, index, limit=100, ids=None):
    # type: (IngestDB, AppDB, FingerprintDB, IndexClientPool, int, Optional[List[int]]) -> int
    """
    Import the given submission into the main fingerprint database
    """
    query = (
        schema.submission.select(schema.submission.c.handled == False)  # noqa: F712
        .order_by(schema.submission.c.mbid.nullslast(), schema.submission.c.id.desc())
    )
    if ids is not None:
        query = query.where(schema.submission.c.id.in_(ids))
    if limit is not None:
        query = query.limit(limit)
    count = 0
    for submission in ingest_db.execute(query):
        import_submission(ingest_db, app_db, fingerprint_db, index, submission)
        count += 1
    logger.debug("Imported %d submissions", count)
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
