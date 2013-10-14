# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
import uuid
from sqlalchemy import sql
from acoustid import tables as schema, const
from acoustid.data.fingerprint import lookup_fingerprint, insert_fingerprint, inc_fingerprint_submission_count, FingerprintSearcher
from acoustid.data.musicbrainz import resolve_mbid_redirect

logger = logging.getLogger(__name__)


def resolve_track_gid(conn, gid):
    query = sql.select([schema.track.c.id, schema.track.c.new_id],
        schema.track.c.gid == gid)
    row = conn.execute(query).first()
    if row is None:
        return None
    track_id, new_track_id = row
    if new_track_id is None:
        return track_id
    query = sql.select([schema.track.c.id],
        schema.track.c.id == new_track_id)
    return conn.execute(query).scalar()


def lookup_mbids(conn, track_ids):
    """
    Lookup MBIDs for the specified AcoustID track IDs.
    """
    if not track_ids:
        return {}
    query = sql.select([
        schema.track_mbid.c.track_id,
        schema.track_mbid.c.mbid,
        schema.track_mbid.c.submission_count,
    ])
    query = query.where(sql.and_(schema.track_mbid.c.track_id.in_(track_ids), schema.track_mbid.c.disabled == False))
    query = query.order_by(schema.track_mbid.c.mbid)
    results = {}
    for track_id, mbid, sources in conn.execute(query):
        results.setdefault(track_id, []).append((mbid, sources))
    return results


def lookup_meta_ids(conn, track_ids):
    if not track_ids:
        return {}
    query = sql.select(
        [schema.track_meta.c.track_id, schema.track_meta.c.meta_id],
        sql.and_(schema.track_meta.c.track_id.in_(track_ids))).order_by(schema.track_meta.c.meta_id)
    results = {}
    for track_id, meta_id in conn.execute(query):
        results.setdefault(track_id, []).append(meta_id)
    return results


def lookup_tracks(conn, mbids):
    if not mbids:
        return {}
    query = sql.select(
        [schema.track_mbid.c.track_id, schema.track.c.gid, schema.track_mbid.c.mbid],
        sql.and_(schema.track_mbid.c.mbid.in_(mbids), schema.track_mbid.c.disabled == False),
        from_obj=schema.track_mbid.join(schema.track, schema.track_mbid.c.track_id == schema.track.c.id)). \
        order_by(schema.track_mbid.c.track_id)
    results = {}
    for track_id, track_gid, mbid in conn.execute(query):
        results.setdefault(mbid, []).append({'id': track_id, 'gid': track_gid})
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
                sql.func.every(schema.track_mbid.c.disabled).label('all_disabled'),
                sql.func.sum(schema.track_mbid.c.submission_count).label('count'),
            ],
            schema.track_mbid.c.mbid.in_(source_mbids + [target_mbid]),
            group_by=schema.track_mbid.c.track_id)
        rows = conn.execute(query).fetchall()
        to_delete = set()
        to_update = []
        for row in rows:
            old_ids = set(row['all_ids'])
            old_ids.remove(row['id'])
            to_delete.update(old_ids)
            to_update.append((old_ids, row))
            if old_ids:
                update_stmt = schema.track_mbid_source.update().where(schema.track_mbid_source.c.track_mbid_id.in_(old_ids))
                conn.execute(update_stmt.values(track_mbid_id=row['id']))
                update_stmt = schema.track_mbid_change.update().where(schema.track_mbid_change.c.track_mbid_id.in_(old_ids))
                conn.execute(update_stmt.values(track_mbid_id=row['id']))
                update_stmt = schema.track_mbid_flag.update().where(schema.track_mbid_flag.c.track_mbid_id.in_(old_ids))
                conn.execute(update_stmt.values(track_mbid_id=row['id']))
        if to_delete:
            delete_stmt = schema.track_mbid.delete().where(
                schema.track_mbid.c.id.in_(to_delete))
            conn.execute(delete_stmt)
        for old_ids, row in to_update:
            update_stmt = schema.track_mbid.update().where(schema.track_mbid.c.id == row['id'])
            conn.execute(update_stmt.values(submission_count=row['count'],
                mbid=target_mbid, disabled=row['all_disabled']))


def merge_missing_mbids(conn):
    """
    Lookup which MBIDs has been merged in MusicBrainz and merge then
    in the AcoustID database as well.
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


def _merge_tracks_gids(conn, name_with_id, target_id, source_ids):
    name = name_with_id.replace('_id', '')
    tab = schema.metadata.tables['track_%s' % name]
    col = tab.columns[name_with_id]
    tab_src = schema.metadata.tables['track_%s_source' % name]
    col_src = tab_src.columns['track_%s_id' % name]
    if name == 'mbid':
        tab_chg = schema.metadata.tables['track_%s_change' % name]
        col_chg = tab_chg.columns['track_%s_id' % name]
        tab_flag = schema.metadata.tables['track_%s_flag' % name]
        col_flag = tab_flag.columns['track_%s_id' % name]
    columns = [
        sql.func.min(tab.c.id).label('id'),
        sql.func.array_agg(tab.c.id).label('all_ids'),
        sql.func.sum(tab.c.submission_count).label('count'),
    ]
    if name == 'mbid':
        columns.append(sql.func.every(schema.track_mbid.c.disabled).label('all_disabled'))
    query = sql.select(columns, tab.c.track_id.in_(source_ids + [target_id]), group_by=col)
    rows = conn.execute(query).fetchall()
    to_delete = set()
    to_update = []
    for row in rows:
        old_ids = set(row['all_ids'])
        old_ids.remove(row['id'])
        to_delete.update(old_ids)
        to_update.append((old_ids, row))
        if old_ids:
            update_stmt = tab_src.update().where(col_src.in_(old_ids))
            conn.execute(update_stmt.values({col_src: row['id']}))
            if name == 'mbid':
                update_stmt = tab_chg.update().where(col_chg.in_(old_ids))
                conn.execute(update_stmt.values({col_chg: row['id']}))
                update_stmt = tab_flag.update().where(col_flag.in_(old_ids))
                conn.execute(update_stmt.values({col_flag: row['id']}))
    if to_delete:
        delete_stmt = tab.delete().where(tab.c.id.in_(to_delete))
        conn.execute(delete_stmt)
    for old_ids, row in to_update:
        update_stmt = tab.update().where(tab.c.id == row['id'])
        if name == 'mbid':
            conn.execute(update_stmt.values(submission_count=row['count'], track_id=target_id, disabled=row['all_disabled']))
        else:
            conn.execute(update_stmt.values(submission_count=row['count'], track_id=target_id))


def merge_tracks(conn, target_id, source_ids):
    """
    Merge the specified tracks.
    """
    logger.info("Merging tracks %s into %s", ', '.join(map(str, source_ids)), target_id)
    with conn.begin():
        _merge_tracks_gids(conn, 'mbid', target_id, source_ids)
        _merge_tracks_gids(conn, 'puid', target_id, source_ids)
        _merge_tracks_gids(conn, 'meta_id', target_id, source_ids)
        _merge_tracks_gids(conn, 'foreignid_id', target_id, source_ids)
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
    insert_stmt = schema.track.insert().values({'gid': str(uuid.uuid4())})
    id = conn.execute(insert_stmt).inserted_primary_key[0]
    logger.debug("Inserted track %r", id)
    return id


def _insert_gid(conn, tab, tab_src, col, name, track_id, gid, submission_id=None, source_id=None):
    cond = sql.and_(tab.c.track_id == track_id, col == gid)
    query = sql.select([tab.c.id], cond)
    id = conn.execute(query).scalar()
    if id is not None:
        update_stmt = tab.update().where(cond)
        values = {'submission_count': sql.text('submission_count+1')}
        conn.execute(update_stmt.values(**values))
    else:
        insert_stmt = tab.insert().values({
            'track_id': track_id, name: gid,
            'submission_count': 1})
        id = conn.execute(insert_stmt).inserted_primary_key[0]
        logger.debug("Added %s %s to track %d", name.upper(), gid, track_id)
    insert_stmt = tab_src.insert().values({
        'track_%s_id' % name.replace('_id', ''): id,
        'submission_id': submission_id,
        'source_id': source_id,
    })
    conn.execute(insert_stmt)
    return True


def insert_mbid(conn, track_id, mbid, submission_id=None, source_id=None):
    return _insert_gid(conn, schema.track_mbid, schema.track_mbid_source,
        schema.track_mbid.c.mbid, 'mbid', track_id, mbid, submission_id, source_id)


def insert_puid(conn, track_id, puid, submission_id=None, source_id=None):
    return _insert_gid(conn, schema.track_puid, schema.track_puid_source,
        schema.track_puid.c.puid, 'puid', track_id, puid, submission_id, source_id)


def insert_track_foreignid(conn, track_id, foreignid_id, submission_id=None, source_id=None):
    return _insert_gid(conn, schema.track_foreignid, schema.track_foreignid_source,
        schema.track_foreignid.c.foreignid_id, 'foreignid_id', track_id, foreignid_id,
        submission_id, source_id)


def insert_track_meta(conn, track_id, meta_id, submission_id=None, source_id=None):
    return _insert_gid(conn, schema.track_meta, schema.track_meta_source,
        schema.track_meta.c.meta_id, 'meta_id', track_id, meta_id, submission_id, source_id)


def calculate_fingerprint_similarity_matrix(conn, track_ids):
    fp1 = schema.fingerprint.alias('fp1')
    fp2 = schema.fingerprint.alias('fp2')
    src = fp1.join(fp2, fp1.c.id < fp2.c.id)
    cond = sql.and_(fp1.c.track_id.in_(track_ids), fp2.c.track_id.in_(track_ids))
    query = sql.select([
        fp1.c.id, fp2.c.id,
        sql.func.acoustid_compare2(fp1.c.fingerprint, fp2.c.fingerprint, const.TRACK_MAX_OFFSET),
    ], cond, from_obj=src).order_by(fp1.c.id, fp2.c.id)
    result = {}
    for fp1_id, fp2_id, score in conn.execute(query):
        result.setdefault(fp1_id, {})[fp2_id] = score
        result.setdefault(fp2_id, {})[fp1_id] = score
        result.setdefault(fp1_id, {})[fp1_id] = 1.0
        result.setdefault(fp2_id, {})[fp2_id] = 1.0
    return result


def can_merge_tracks(conn, track_ids):
    fp1 = schema.fingerprint.alias('fp1')
    fp2 = schema.fingerprint.alias('fp2')
    join_cond = sql.and_(fp1.c.id < fp2.c.id, fp1.c.track_id < fp2.c.track_id)
    src = fp1.join(fp2, join_cond)
    cond = sql.and_(fp1.c.track_id.in_(track_ids), fp2.c.track_id.in_(track_ids))
    query = sql.select([
        fp1.c.track_id, fp2.c.track_id,
        sql.func.max(sql.func.abs(fp1.c.length - fp2.c.length)),
        sql.func.min(sql.func.acoustid_compare2(fp1.c.fingerprint, fp2.c.fingerprint, const.TRACK_MAX_OFFSET)),
    ], cond, from_obj=src).group_by(fp1.c.track_id, fp2.c.track_id).order_by(fp1.c.track_id, fp2.c.track_id)
    rows = conn.execute(query)
    merges = {}
    for fp1_id, fp2_id, length_diff, score in rows:
        if score < const.TRACK_GROUP_MERGE_THRESHOLD:
            continue
        if length_diff > const.FINGERPRINT_MAX_LENGTH_DIFF:
            continue
        group = fp1_id
        if group in merges:
            group = merges[group]
        merges[fp2_id] = group
    result = []
    for group in set(merges.values()):
        result.append(set([group] + [i for i in merges if merges[i] == group]))
    return result


def can_add_fp_to_track(conn, track_id, fingerprint, length):
    cond = schema.fingerprint.c.track_id == track_id
    query = sql.select([
        sql.func.acoustid_compare2(schema.fingerprint.c.fingerprint, fingerprint, const.TRACK_MAX_OFFSET),
        schema.fingerprint.c.length,
    ], cond, from_obj=schema.fingerprint)
    for fp_score, fp_length in conn.execute(query):
        if fp_score < const.TRACK_GROUP_MERGE_THRESHOLD:
            return False
        if abs(fp_length - length) > const.FINGERPRINT_MAX_LENGTH_DIFF:
            return False
    return True


def find_track_duplicates(conn, fingerprint, index=None):
    with conn.begin():
        searcher = FingerprintSearcher(conn, index)
        searcher.min_score = const.TRACK_MERGE_THRESHOLD
        matches = searcher.search(fingerprint['fingerprint'], fingerprint['length'])
        if not matches:
            logger.debug("Not matched itself!")
            return
        logged = False
        match = matches[0]
        all_track_ids = set()
        possible_track_ids = set()
        for m in matches:
            if m['track_id'] in all_track_ids:
                continue
            all_track_ids.add(m['track_id'])
            if can_add_fp_to_track(conn, m['track_id'], fingerprint['fingerprint'], fingerprint['length']):
                if m['id'] != fingerprint['id']:
                    if not logged:
                        logger.debug("Deduplicating fingerprint %d", fingerprint['id'])
                        logged = True
                    logger.debug("Fingerprint %d with track %d is %d%% similar", m['id'], m['track_id'], m['score'] * 100)
                possible_track_ids.add(m['track_id'])
        if len(possible_track_ids) > 1:
            for group in can_merge_tracks(conn, possible_track_ids):
                if len(group) > 1:
                    target_track_id = min(group)
                    group.remove(target_track_id)
                    #logger.debug("Would like to merge tracks %r into %d", list(group), target_track_id)
                    merge_tracks(conn, target_track_id, list(group))
                    #raise Exception(1)
                    break
        conn.execute("INSERT INTO fingerprint_deduplicate (id) VALUES (%s)", fingerprint['id'])


def find_duplicates(conn, limit=50, index=None):
    query = "SELECT f.id, fingerprint, length FROM fingerprint f LEFT JOIN fingerprint_deduplicate d ON f.id=d.id WHERE d.id IS NULL ORDER BY f.id LIMIT 1000"
    for fingerprint in conn.execute(query):
        find_track_duplicates(conn, fingerprint, index=index)

