# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables as schema

logger = logging.getLogger(__name__)


def insert_meta(conn, values):
    with conn.begin():
        insert_stmt = schema.meta.insert().values(**values)
        id = conn.execute(insert_stmt).inserted_primary_key[0]
        logger.debug("Inserted meta %d with values %r", id, values)
    return id

def lookup_meta(conn, meta_ids):
    if not meta_ids:
        return []
    query = schema.meta.select(schema.meta.c.id.in_(meta_ids))
    results = []
    for row in conn.execute(query):
        result = {
            '_no_ids': True,
            'recording_id': row['id'],
            'recording_title': row['track'],
            'recording_artists': [],
            'recording_duration': None,
            'track_id': row['id'],
            'track_position': row['track_no'],
            'track_title': row['track'],
            'track_artists': [],
            'track_duration': None,
            'medium_position': row['disc_no'],
            'medium_format': None,
            'medium_title': None,
            'medium_track_count': None,
            'release_rid': row['id'],
            'release_id': row['id'],
            'release_title': row['album'],
            'release_artists': [],
            'release_medium_count': None,
            'release_track_count': None,
            'release_events': [{
                'release_date_year': row['year'],
                'release_date_month': None,
                'release_date_day': None,
                'release_country': '',
            }],
            'release_group_id': row['id'],
            'release_group_title': row['album'],
            'release_group_artists': [],
            'release_group_primary_type': None,
            'release_group_secondary_types': [],
        }
        if row['artist']:
            result['recording_artists'].append(row['artist'])
            result['track_artists'].append(row['artist'])
        if row['album_artist']:
            result['release_artists'].append(row['album_artist'])
            result['release_group_artists'].append(row['album_artist'])
        results.append(result)
    return results

