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
        schema.track_mbid.c.track_id.in_(track_ids))
    results = {}
    for track_id, mbid in conn.execute(query):
        results.setdefault(track_id, []).append(mbid)
    return results


def merge_mbids(conn, target_mbid, source_mbids):
    """
    Merge the specified MBIDs.
    """
    logger.info("Merging MBIDs %s into %s", ', '.join(source_mbids), target_mbid)
    with conn.begin():
        query = sql.select(
            [schema.track_mbid.c.track_id, schema.track_mbid.c.mbid],
            schema.track_mbid.c.mbid.in_(source_mbids + [target_mbid]))
        rows = conn.execute(query).fetchall()
        source_track_ids = set([r[0] for r in rows if r[1] != target_mbid])
        target_track_ids = set([r[0] for r in rows if r[1] == target_mbid])
        missing_track_ids = source_track_ids - target_track_ids
        if missing_track_ids:
            conn.execute(schema.track_mbid.insert(),
                [{'track_id': track_id, 'mbid': target_mbid}
                    for track_id in missing_track_ids])
        delete_stmt = schema.track_mbid.delete().where(
            schema.track_mbid.c.mbid.in_(source_mbids))
        conn.execute(delete_stmt)


def merge_missing_mbids(conn):
    """
    Lookup which MBIDs has been merged in MusicBrainz and merge then
    in the Acoustid database as well.
    """
    logger.debug("Merging missing MBIDs")
    results = conn.execute("""
        SELECT DISTINCT tm.mbid AS old_mbid, mt.gid AS new_mbid
        FROM track_mbid tm
        JOIN musicbrainz.gid_redirect mgr ON tm.mbid = mgr.gid
        JOIN musicbrainz.track mt ON mt.id = mgr.newid
        WHERE mgr.tbl=3
    """)
    merge = {}
    for old_mbid, new_mbid in results:
        merge.setdefault(new_mbid, []).append(old_mbid)
    for new_mbid, old_mbids in merge.iteritems():
        merge_mbids(conn, new_mbid, old_mbids)


def merge_tracks(conn, target_id, source_ids):
    """
    Merge the specified tracks.
    """
    logger.info("Merging tracks %s into %s", ', '.join(source_ids), target_id)
    with conn.begin():
        query = sql.select(
            [schema.track_mbid.c.track_id, schema.track_mbid.c.mbid],
            schema.track_mbid.c.track_id.in_(source_ids + [target_id]))
        rows = conn.execute(query).fetchall()
        source_track_mbids = set([r[1] for r in rows if r[0] != target_id])
        target_track_mbids = set([r[1] for r in rows if r[0] == target_id])
        missing_track_mbids = source_track_mbids - target_track_mbids
        if missing_track_mbids:
            conn.execute(schema.track_mbid.insert(),
                [{'track_id': target_id, 'mbid': mbid}
                    for mbid in missing_track_mbids])
        # XXX don't move duplicate fingerprints
        update_stmt = schema.fingerprint.update().where(
            schema.track_mbid.c.track_id.in_(source_ids))
        conn.execute(update_stmt.values(track_id=target_id))
        delete_stmt = schema.track_mbid.delete().where(
            schema.track_mbid.c.track_id.in_(source_ids))
        conn.execute(delete_stmt)


def insert_track(conn):
    """
    Insert a new track into the database
    """
    insert_stmt = schema.track.insert()
    id = conn.execute(insert_stmt).inserted_primary_key[0]
    logger.debug("Inserted track %r", id)
    return id


def insert_mbid(conn, track_id, mbid):
    query = sql.select([1], sql.and_(
        schema.track_mbid.c.track_id == track_id,
        schema.track_mbid.c.mbid == mbid), schema.track_mbid)
    if conn.execute(query).scalar():
        return False
    insert_stmt = schema.track_mbid.insert().values({
        'track_id': track_id, 'mbid': mbid})
    conn.execute(insert_stmt)
    logger.debug("Added MBID %s to track %d", mbid, track_id)
    return True

