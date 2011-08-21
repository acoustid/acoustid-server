# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables as schema, const
from acoustid.data.fingerprint import lookup_fingerprint, insert_fingerprint, inc_fingerprint_submission_count
from acoustid.data.musicbrainz import find_puid_mbids, resolve_mbid_redirect
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


def import_submission(conn, submission):
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
        if submission['puid']:
            min_duration = submission['length'] - 15
            max_duration = submission['length'] + 15
            mbids.extend(find_puid_mbids(conn, submission['puid'], min_duration, max_duration))
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
        matches = lookup_fingerprint(conn,
            submission['fingerprint'], submission['length'],
            const.FINGERPRINT_MERGE_THRESHOLD,
            const.TRACK_MERGE_THRESHOLD, fast=True, max_offset=const.TRACK_MAX_OFFSET)
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
            if match['score'] > const.FINGERPRINT_MERGE_THRESHOLD:
                fingerprint['id'] = match['id']
            all_track_ids = set()
            possible_track_ids = set()
            for m in matches:
                if m['track_id'] not in all_track_ids:
                    logger.debug("Fingerprint %d with track %d is %d%% similar", m['id'], m['track_id'], m['score'] * 100)
                    if can_add_fp_to_track(conn, m['track_id'], submission['fingerprint'], submission['length']):
                        possible_track_ids.add(m['track_id'])
                        if not fingerprint['track_id']:
                            fingerprint['track_id'] = m['track_id']
                    all_track_ids.add(m['track_id'])
            if len(possible_track_ids) > 1:
                for group in can_merge_tracks(conn, possible_track_ids):
                    if match['track_id'] in group and len(group) > 1:
                        fingerprint['track_id'] = min(group)
                        group.remove(fingerprint['track_id'])
                        merge_tracks(conn, fingerprint['track_id'], list(group))
                        break
        if not fingerprint['track_id']:
            fingerprint['track_id'] = insert_track(conn)
        if not fingerprint['id']:
            fingerprint['id'] = insert_fingerprint(conn, fingerprint, submission['id'], submission['source_id'])
        else:
            inc_fingerprint_submission_count(conn, fingerprint['id'])
        for mbid in mbids:
            insert_mbid(conn, fingerprint['track_id'], mbid, submission['id'], submission['source_id'])
        if submission['puid'] and submission['puid'] != '00000000-0000-0000-0000-000000000000':
            insert_puid(conn, fingerprint['track_id'], submission['puid'], submission['id'], submission['source_id'])
        if submission['meta_id']:
            insert_track_meta(conn, fingerprint['track_id'], submission['meta_id'], submission['id'], submission['source_id'])
        if submission['foreignid_id']:
            insert_track_foreignid(conn, fingerprint['track_id'], submission['foreignid_id'], submission['id'], submission['source_id'])
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

