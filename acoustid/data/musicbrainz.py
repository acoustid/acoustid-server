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
    query = sql.select(
        [
            schema.mb_track.c.gid,
            schema.mb_track.c.name,
            schema.mb_track.c.length,
            schema.mb_artist.c.gid.label('artist_gid'),
            schema.mb_artist.c.name.label('artist_name')
        ],
        schema.mb_track.c.gid.in_(mbids),
        from_obj=schema.mb_track.join(schema.mb_artist))
    results = {}
    for row in conn.execute(query):
        results[row['gid']] = {
            'id': row['gid'],
            'name': row['name'],
            'length': row['length'] / 1000,
            'artist_id': row['artist_gid'],
            'artist_name': row['artist_name'],
        }
    return results

