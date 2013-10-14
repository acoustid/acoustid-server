# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables as schema, const
from acoustid.data.fingerprint import lookup_fingerprint, insert_fingerprint, inc_fingerprint_submission_count, FingerprintSearcher
from acoustid.data.musicbrainz import resolve_mbid_redirect
from acoustid.data.track import insert_track, insert_mbid, insert_puid, merge_tracks, insert_track_meta, can_add_fp_to_track, can_merge_tracks, insert_track_foreignid

logger = logging.getLogger(__name__)


def insert_submission(conn, data):
    """
    Insert a new submission into the database
    """
    with conn.begin():
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
        id = conn.execute(insert_stmt).inserted_primary_key[0]
    logger.debug("Inserted submission %r with data %r", id, data)
    return id


def import_submission(conn, submission, index=None):
    """
    Import the given submission into the main fingerprint database
    """
    with conn.begin():
        update_stmt = schema.submission.update().where(
            schema.submission.c.id == submission['id'])
        conn.execute(update_stmt.values(handled=True))
        mbids = []
        if submission['mbid']:
            mbids.append(resolve_mbid_redirect(conn, submission['mbid']))
        logger.info("Importing submission %d with MBIDs %s",
            submission['id'], ', '.join(mbids))
        num_unique_items = len(set(submission['fingerprint']))
        if num_unique_items < const.FINGERPRINT_MIN_UNIQUE_ITEMS:
            logger.info("Skipping, has only %d unique items", num_unique_items)
            return
        num_query_items = conn.execute("SELECT icount(acoustid_extract_query(%(fp)s))", dict(fp=submission['fingerprint']))
        if not num_query_items:
            logger.info("Skipping, no data to index")
            return
        searcher = FingerprintSearcher(conn, index, fast=False)
        searcher.min_score = const.TRACK_MERGE_THRESHOLD
        matches = searcher.search(submission['fingerprint'], submission['length'])
        fingerprint = {
            'id': None,
            'track_id': None,
            'fingerprint': submission['fingerprint'],
            'length': submission['length'],
            'bitrate': submission['bitrate'],
            'format_id': submission['format_id'],
        }
        if matches:
            match = matches[0]
            all_track_ids = set()
            possible_track_ids = set()
            for m in matches:
                if m['track_id'] in all_track_ids:
                    continue
                all_track_ids.add(m['track_id'])
                logger.debug("Fingerprint %d with track %d is %d%% similar", m['id'], m['track_id'], m['score'] * 100)
                if can_add_fp_to_track(conn, m['track_id'], submission['fingerprint'], submission['length']):
                    possible_track_ids.add(m['track_id'])
                    if not fingerprint['track_id']:
                        fingerprint['track_id'] = m['track_id']
                        if m['score'] > const.FINGERPRINT_MERGE_THRESHOLD:
                            fingerprint['id'] = m['id']
            if len(possible_track_ids) > 1:
                for group in can_merge_tracks(conn, possible_track_ids):
                    if fingerprint['track_id'] in group and len(group) > 1:
                        fingerprint['track_id'] = min(group)
                        group.remove(fingerprint['track_id'])
                        merge_tracks(conn, fingerprint['track_id'], list(group))
                        break
        if not fingerprint['track_id']:
            fingerprint['track_id'] = insert_track(conn)
        if not fingerprint['id']:
            fingerprint['id'] = insert_fingerprint(conn, fingerprint, submission['id'], submission['source_id'])
        else:
            inc_fingerprint_submission_count(conn, fingerprint['id'], submission['id'], submission['source_id'])
        for mbid in mbids:
            insert_mbid(conn, fingerprint['track_id'], mbid, submission['id'], submission['source_id'])
        if submission['puid'] and submission['puid'] != '00000000-0000-0000-0000-000000000000':
            insert_puid(conn, fingerprint['track_id'], submission['puid'], submission['id'], submission['source_id'])
        if submission['meta_id']:
            insert_track_meta(conn, fingerprint['track_id'], submission['meta_id'], submission['id'], submission['source_id'])
        if submission['foreignid_id']:
            insert_track_foreignid(conn, fingerprint['track_id'], submission['foreignid_id'], submission['id'], submission['source_id'])
        return fingerprint


def import_queued_submissions(conn, index=None, limit=100, ids=None):
    """
    Import the given submission into the main fingerprint database
    """
    query = schema.submission.select(schema.submission.c.handled == False).\
        order_by(schema.submission.c.mbid.nullslast(), schema.submission.c.id.desc())
    if ids is not None:
        query = query.where(schema.submission.c.id.in_(ids))
    if limit is not None:
        query = query.limit(limit)
    count = 0
    for submission in conn.execute(query):
        import_submission(conn, submission, index=index)
        count += 1
    logger.debug("Imported %d submissions", count)
    return count


def lookup_submission_status(db, ids):
    if not ids:
        return {}
    source = schema.fingerprint_source.\
        join(schema.fingerprint).\
        join(schema.track)
    query = sql.select([schema.fingerprint_source.c.submission_id, schema.track.c.gid], from_obj=source).\
        where(schema.fingerprint_source.c.submission_id.in_(ids))
    results = {}
    for id, track_gid in db.execute(query):
        results[id] = track_gid
    return results

