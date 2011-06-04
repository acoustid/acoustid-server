# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables as schema

logger = logging.getLogger(__name__)


def load_artists(conn, artist_credit_ids):
    if not artist_credit_ids:
        return {}
    src = schema.mb_artist_credit_name
    src = src.join(schema.mb_artist)
    condition = schema.mb_artist_credit_name.c.artist_credit.in_(artist_credit_ids)
    columns = [
        schema.mb_artist_credit_name.c.name,
        schema.mb_artist_credit_name.c.artist_credit,
        schema.mb_artist.c.gid
    ]
    query = sql.select(columns, condition, from_obj=src)
    result = {}
    for row in conn.execute(query):
        result.setdefault(row['artist_credit'], []).append({
            'id': row['gid'],
            'name': row['name']
        })
    return result


def lookup_metadata(conn, mbids):
    """
    Lookup MusicBrainz metadata for the specified MBIDs.
    """
    if not mbids:
        return {}
    src = schema.mb_recording
    src = src.join(schema.mb_track, schema.mb_recording.c.id == schema.mb_track.c.recording)
    src = src.join(schema.mb_tracklist, schema.mb_track.c.tracklist == schema.mb_tracklist.c.id)
    src = src.join(schema.mb_medium, schema.mb_tracklist.c.id == schema.mb_medium.c.tracklist)
    src = src.join(schema.mb_release, schema.mb_medium.c.release == schema.mb_release.c.id)
    src = src.outerjoin(schema.mb_medium_format, schema.mb_medium.c.format == schema.mb_medium_format.c.id)
    condition = schema.mb_recording.c.gid.in_(mbids)
    columns = [
        schema.mb_recording.c.gid,
        schema.mb_track.c.name,
        schema.mb_track.c.length,
        schema.mb_track.c.artist_credit.label('_artist_credit_id'),
        schema.mb_track.c.position.label('track_num'),
        schema.mb_medium.c.position.label('disc_num'),
        schema.mb_tracklist.c.track_count.label('total_tracks'),
        schema.mb_release.c.gid.label('release_id'),
        schema.mb_release.c.name.label('release_name'),
        schema.mb_medium_format.c.name.label('medium_format'),
    ]
    query = sql.select(columns, condition, from_obj=src).order_by(schema.mb_track.c.id, schema.mb_release.c.id)
    artist_credit_ids = set()
    results = {}
    i = 0
    for row in conn.execute(query):
        i += 1
        result = dict(row)
        result['length'] /= 1000
        results.setdefault(row['gid'], []).append(result)
        artist_credit_ids.add(row['_artist_credit_id'])
    print i
    artists = load_artists(conn, artist_credit_ids)
    for tracks in results.itervalues():
        for result in tracks:
            result['artists'] = artists[result.pop('_artist_credit_id')]
    return results


def lookup_recording_metadata(conn, mbids):
    """
    Lookup MusicBrainz metadata for the specified MBIDs.
    """
    if not mbids:
        return {}
    src = schema.mb_track.join(schema.mb_artist)
    query = sql.select(
        [
            schema.mb_track.c.gid,
            schema.mb_track.c.name,
            schema.mb_track.c.length,
            schema.mb_artist.c.gid.label('artist_id'),
            schema.mb_artist.c.name.label('artist_name'),
        ],
        schema.mb_track.c.gid.in_(mbids),
        from_obj=src)
    results = {}
    for row in conn.execute(query):
        result = dict(row)
        result['length'] /= 1000
        results[row['gid']] = result
    return results


def find_puid_mbids(conn, puid, min_duration, max_duration):
    """
    Find MBIDs for MusicBrainz tracks that are linked to the given PUID and
    have duration within the given range
    """
    src = schema.mb_puid
    src = src.join(schema.mb_recording_puid, schema.mb_recording_puid.c.puid == schema.mb_puid.c.id)
    src = src.join(schema.mb_recording, schema.mb_recording.c.id == schema.mb_recording_puid.c.recording)
    condition = sql.and_(
        schema.mb_puid.c.puid == puid,
        schema.mb_recording.c.length.between(min_duration * 1000, max_duration * 1000))
    query = sql.select([schema.mb_recording.c.gid], condition, from_obj=src)
    return [r[0] for r in conn.execute(query)]
