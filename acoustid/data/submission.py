# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables as schema
from acoustid.data.fingerprint import lookup_fingerprint, insert_fingerprint
from acoustid.data.musicbrainz import find_puid_mbids, resolve_mbid_redirect
from acoustid.data.track import insert_track, insert_mbid, merge_tracks

logger = logging.getLogger(__name__)

TRACK_MERGE_TRESHOLD = 0.7
FINGERPRINT_MERGE_TRESHOLD = 0.95
FINGERPRINT_MIN_UNIQUE_ITEMS = 30


def insert_submission(conn, data):
    """
    Insert a new submission into the database
    """
    with conn.begin():
        insert_stmt = schema.submission.insert().values({
            'fingerprint': data['fingerprint'],
            'length': data['length'],
            'bitrate': data.get('bitrate'),
            'source_id': data['source_id'],
            'mbid': data.get('mbid'),
            'puid': data.get('puid'),
            'format_id': data.get('format_id'),
            'meta_id': data.get('meta_id'),
        })
        id = conn.execute(insert_stmt).inserted_primary_key[0]
    logger.debug("Inserted submission %r with data %r", id, data)
    return id


def import_submission(conn, submission):
    """
    Import the given submission into the main fingerprint database
    """
    with conn.begin():
        mbids = []
        if submission['mbid']:
            mbids.append(resolve_mbid_redirect(submission['mbid']))
        if submission['puid']:
            min_duration = submission['length'] - 15
            max_duration = submission['length'] + 15
            mbids.extend(find_puid_mbids(conn, submission['puid'], min_duration, max_duration))
        logger.info("Importing submission %d with MBIDs %s",
            submission['id'], ', '.join(mbids))
        update_stmt = schema.submission.update().where(
            schema.submission.c.id == submission['id'])
        conn.execute(update_stmt.values(handled=True))
        num_unique_items = len(set(submission['fingerprint']))
        if num_unique_items < FINGERPRINT_MIN_UNIQUE_ITEMS:
            logger.info("Skipping, has only %d unique items", num_unique_items)
            return
        num_query_items = conn.execute("SELECT icount(extract_fp_query(%(fp)s))", dict(fp=submission['fingerprint']))
        if not num_query_items:
            logger.info("Skipping, no data to index")
            return
        matches = lookup_fingerprint(conn,
            submission['fingerprint'], submission['length'],
            FINGERPRINT_MERGE_TRESHOLD, TRACK_MERGE_TRESHOLD, fast=True)
        fingerprint = {
            'id': None,
            'track_id': None,
            'fingerprint': submission['fingerprint'],
            'length': submission['length'],
            'bitrate': submission['bitrate'],
            'source_id': submission['source_id'],
            'submission_id': submission['id'],
            'format_id': submission['format_id'],
            'meta_id': submission['meta_id'],
        }
        if matches:
            match = matches[0]
            logger.debug("Matches %d results, the top result %s with track %d is %d%% similar",
                len(matches), match['id'], match['track_id'], match['score'] * 100)
            fingerprint['track_id'] = match['track_id']
            if match['score'] > FINGERPRINT_MERGE_TRESHOLD:
                fingerprint['id'] = match['id']
            all_track_ids = set([match['track_id']])
            for m in matches:
                if m['track_id'] not in all_track_ids:
                    logger.debug("Fingerprint %d with track %d is %d%% similar",
                        m['id'], m['track_id'], m['score'] * 100)
                    all_track_ids.add(m['track_id'])
            if len(all_track_ids) > 1:
                all_track_ids.remove(match['track_id'])
                merge_tracks(conn, match['track_id'], list(all_track_ids))
        if not fingerprint['track_id']:
            fingerprint['track_id'] = insert_track(conn)
            logger.info('Added new track %d', fingerprint['track_id'])
        if not fingerprint['id']:
            fingerprint['id'] = insert_fingerprint(conn, fingerprint)
            logger.info('Added new fingerprint %d', fingerprint['id'])
        for mbid in mbids:
            if insert_mbid(conn, fingerprint['track_id'], mbid):
                logger.info('Added MBID %s to track %d', mbid, fingerprint['track_id'])
        return fingerprint


def import_queued_submissions(conn, limit=50):
    """
    Import the given submission into the main fingerprint database
    """
    query = schema.submission.select(schema.submission.c.handled == False).limit(limit)
    count = 0
    for submission in conn.execute(query):
        import_submission(conn, submission)
        count += 1
    logger.debug("Imported %d submissions", count)

