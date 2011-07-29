# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables as schema

logger = logging.getLogger(__name__)


def lookup_mbids(conn, track_ids):
    """
    Lookup MBIDs for the specified Acoustid track IDs.
    """
    if not track_ids:
        return {}
    query = sql.select(
        [schema.track_mbid.c.track_id, schema.track_mbid.c.mbid],
        schema.track_mbid.c.track_id.in_(track_ids)).order_by(schema.track_mbid.c.mbid)
    results = {}
    for track_id, mbid in conn.execute(query):
        results.setdefault(track_id, []).append(mbid)
    return results


def lookup_tracks(conn, mbids):
    if not mbids:
        return {}
    query = sql.select(
        [schema.track_mbid.c.track_id, schema.track_mbid.c.mbid],
        schema.track_mbid.c.mbid.in_(mbids)).order_by(schema.track_mbid.c.track_id)
    results = {}
    for track_id, mbid in conn.execute(query):
        results.setdefault(mbid, []).append(track_id)
    return results


def merge_mbids(conn, target_mbid, source_mbids):
    """
    Merge the specified MBIDs.
    """
    logger.info("Merging MBIDs %s into %s", ', '.join(source_mbids), target_mbid)
    with conn.begin():
        query = sql.select(
            [
                sql.func.min(schema.track_mbid.c.id).label('id'),
                sql.func.array_agg(schema.track_mbid.c.id).label('all_ids'),
                schema.track_mbid.c.track_id,
                sql.func.sum(schema.track_mbid.c.submission_count).label('count'),
            ],
            schema.track_mbid.c.mbid.in_(source_mbids + [target_mbid]),
            group_by=schema.track_mbid.c.track_id)
        rows = conn.execute(query).fetchall()
        to_delete = set()
        to_update = []
        for row in rows:
            to_update.append((row['id'], row['count']))
            to_delete.update(row['all_ids'])
            to_delete.remove(row['id'])
        if to_delete:
            delete_stmt = schema.track_mbid.delete().where(
                schema.track_mbid.c.id.in_(to_delete))
            conn.execute(delete_stmt)
        for id, count in to_update:
            update_stmt = schema.track_mbid.update().where(schema.track_mbid.c.id == id)
            conn.execute(update_stmt.values(submission_count=count, mbid=target_mbid))


def merge_missing_mbids(conn):
    """
    Lookup which MBIDs has been merged in MusicBrainz and merge then
    in the Acoustid database as well.
    """
    logger.debug("Merging missing MBIDs")
    results = conn.execute("""
        SELECT DISTINCT tm.mbid AS old_mbid, mt.gid AS new_mbid
        FROM track_mbid tm
        JOIN musicbrainz.recording_gid_redirect mgr ON tm.mbid = mgr.gid
        JOIN musicbrainz.recording mt ON mt.id = mgr.new_id
    """)
    merge = {}
    for old_mbid, new_mbid in results:
        merge.setdefault(new_mbid, []).append(old_mbid)
    for new_mbid, old_mbids in merge.iteritems():
        merge_mbids(conn, new_mbid, old_mbids)


def _merge_tracks_gids(conn, tab, col, target_id, source_ids):
    query = sql.select(
        [
            sql.func.min(tab.c.id).label('id'),
            sql.func.array_agg(tab.c.id).label('all_ids'),
            sql.func.sum(tab.c.submission_count).label('count'),
        ],
        tab.c.id.in_(source_ids + [target_id]),
        group_by=col)
    rows = conn.execute(query).fetchall()
    to_delete = set()
    to_update = []
    for row in rows:
        to_update.append((row['id'], row['count']))
        to_delete.update(row['all_ids'])
        to_delete.remove(row['id'])
    if to_delete:
        delete_stmt = tab.delete().where(tab.c.id.in_(to_delete))
        conn.execute(delete_stmt)
    for id, count in to_update:
        update_stmt = tab.update().where(tab.c.id == id)
        conn.execute(update_stmt.values(submission_count=count, track_id=target_id))


def merge_tracks(conn, target_id, source_ids):
    """
    Merge the specified tracks.
    """
    logger.info("Merging tracks %s into %s", ', '.join(map(str, source_ids)), target_id)
    with conn.begin():
        _merge_tracks_gids(conn, schema.track_mbid, schema.track_mbid.c.mbid, target_id, source_ids)
        _merge_tracks_gids(conn, schema.track_puid, schema.track_puid.c.puid, target_id, source_ids)
        # XXX don't move duplicate fingerprints
        update_stmt = schema.fingerprint.update().where(
            schema.fingerprint.c.track_id.in_(source_ids))
        conn.execute(update_stmt.values(track_id=target_id))
        update_stmt = schema.track.update().where(
            sql.or_(schema.track.c.id.in_(source_ids),
                    schema.track.c.new_id.in_(source_ids)))
        conn.execute(update_stmt.values(new_id=target_id))


def insert_track(conn):
    """
    Insert a new track into the database
    """
    insert_stmt = schema.track.insert()
    id = conn.execute(insert_stmt).inserted_primary_key[0]
    logger.debug("Inserted track %r", id)
    return id


def insert_mbid(conn, track_id, mbid):
    cond = sql.and_(
        schema.track_mbid.c.track_id == track_id,
        schema.track_mbid.c.mbid == mbid)
    query = sql.select([1], cond, schema.track_mbid)
    if conn.execute(query).scalar():
        update_stmt = schema.track_mbid.update().where(cond)
        conn.execute(update_stmt.values(submission_count=sql.text('submission_count+1')))
        return False
    insert_stmt = schema.track_mbid.insert().values({
        'track_id': track_id, 'mbid': mbid,
        'submission_count': 1})
    conn.execute(insert_stmt)
    logger.debug("Added MBID %s to track %d", mbid, track_id)
    return True


def insert_puid(conn, track_id, puid):
    cond = sql.and_(
        schema.track_puid.c.track_id == track_id,
        schema.track_puid.c.puid == puid)
    query = sql.select([1], cond, schema.track_puid)
    if conn.execute(query).scalar():
        update_stmt = schema.track_puid.update().where(cond)
        conn.execute(update_stmt.values(submission_count=sql.text('submission_count+1')))
        return False
    insert_stmt = schema.track_puid.insert().values({
        'track_id': track_id, 'puid': puid,
        'submission_count': 1})
    conn.execute(insert_stmt)
    logger.debug("Added PUID %s to track %d", puid, track_id)
    return True


def get_track_fingerprint_matrix(conn, track_id):
    query = """
        SELECT
            f1.id AS fp1_id,
            f2.id AS fp2_id,
            CASE WHEN f1.id = f2.id
                THEN 1.0
                ELSE acoustid_compare(f1.fingerprint, f2.fingerprint)
            END AS score
        FROM fingerprint f1
        JOIN fingerprint f2 ON f1.id <= f2.id AND f2.track_id = f1.track_id
        WHERE f1.track_id = %s
        ORDER BY f1.id, f2.id
    """
    rows = conn.execute(query, (track_id,))
    result = {}
    for fp1_id, fp2_id, score in rows:
        result.setdefault(fp1_id, {})[fp2_id] = score
        result.setdefault(fp2_id, {})[fp1_id] = score
    return result

