# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

import logging
from sqlalchemy import sql
from acoustid import tables as schema

logger = logging.getLogger(__name__)


def lookup_metadata(conn, mbids):
    """
    Lookup MusicBrainz metadata for the specified MBIDs.
    """
    src = schema.mb_track.join(schema.mb_artist)
    src = src.join(schema.mb_album_track, schema.mb_album_track.c.track == schema.mb_track.c.id)
    src = src.join(schema.mb_album, schema.mb_album.c.id == schema.mb_album_track.c.album)
    src = src.join(schema.mb_album_meta, schema.mb_album_meta.c.id == schema.mb_album.c.id)
    query = sql.select(
        [
            schema.mb_track.c.gid,
            schema.mb_track.c.name,
            schema.mb_track.c.length,
            schema.mb_artist.c.gid.label('artist_id'),
            schema.mb_artist.c.name.label('artist_name'),
            schema.mb_album.c.gid.label('release_id'),
            schema.mb_album.c.name.label('release_name'),
            schema.mb_album_track.c.sequence.label('track_num'),
            schema.mb_album_meta.c.tracks.label('total_tracks'),
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
    src = src.join(schema.mb_puid_track, schema.mb_puid_track.c.puid == schema.mb_puid.c.id)
    src = src.join(schema.mb_track, schema.mb_track.c.id == schema.mb_puid_track.c.track)
    condition = sql.and_(
        schema.mb_puid.c.puid == puid,
        schema.mb_track.c.length.between(min_duration * 1000, max_duration * 1000))
    query = sql.select([schema.mb_track.c.gid], condition, from_obj=src)
    return [r[0] for r in conn.execute(query)]
