# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
import re
from sqlalchemy import sql
from acoustid import tables as schema

logger = logging.getLogger(__name__)


def _load_artists(conn, artist_credit_ids):
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


def lookup_metadata(conn, recording_ids, load_releases=False, load_release_groups=False, load_artists=False):
    if not recording_ids:
        return []
    src = schema.mb_recording
    columns = [
        schema.mb_recording.c.gid.label('recording_id'),
        schema.mb_recording.c.artist_credit.label('recording_artist_credit'),
        schema.mb_recording.c.name.label('recording_title'),
        (schema.mb_recording.c.length / 1000).label('recording_duration'),
    ]
    if load_releases:
        src = src.join(schema.mb_track, schema.mb_recording.c.id == schema.mb_track.c.recording)
        src = src.join(schema.mb_tracklist, schema.mb_track.c.tracklist == schema.mb_tracklist.c.id)
        src = src.join(schema.mb_medium, schema.mb_tracklist.c.id == schema.mb_medium.c.tracklist)
        src = src.join(schema.mb_release, schema.mb_medium.c.release == schema.mb_release.c.id)
        src = src.outerjoin(schema.mb_country, schema.mb_release.c.country == schema.mb_country.c.id)
        src = src.outerjoin(schema.mb_medium_format, schema.mb_medium.c.format == schema.mb_medium_format.c.id)
        columns.extend([
            schema.mb_track.c.position.label('track_position'),
            schema.mb_track.c.name.label('track_title'),
            schema.mb_track.c.artist_credit.label('track_artist_credit'),
            (schema.mb_track.c.length / 1000).label('track_duration'),
            schema.mb_medium.c.position.label('medium_position'),
            schema.mb_medium_format.c.name.label('medium_format'),
            schema.mb_tracklist.c.track_count.label('medium_track_count'),
            schema.mb_release.c.gid.label('release_id'),
            schema.mb_release.c.name.label('release_title'),
            schema.mb_release.c.artist_credit.label('release_artist_credit'),
            schema.mb_release.c.date_year.label('release_date_year'),
            schema.mb_release.c.date_month.label('release_date_month'),
            schema.mb_release.c.date_day.label('release_date_day'),
            schema.mb_country.c.iso_code.label('release_country'),
        ])
        if load_release_groups:
            src = src.join(schema.mb_release_group, schema.mb_release.c.release_group == schema.mb_release_group.c.id)
            src = src.outerjoin(schema.mb_release_group_type, schema.mb_release_group.c.type == schema.mb_release_group_type.c.id)
            columns.extend([
                schema.mb_release_group.c.gid.label('release_group_id'),
                schema.mb_release_group.c.name.label('release_group_title'),
                schema.mb_release_group.c.artist_credit.label('release_group_artist_credit'),
                schema.mb_release_group_type.c.name.label('release_group_type'),
            ])
    condition = schema.mb_recording.c.gid.in_(recording_ids)
    query = sql.select(columns, condition, from_obj=src)
    results = []
    artist_credit_ids = set()
    for row in conn.execute(query):
        results.append(dict(row))
        artist_credit_ids.add(row['recording_artist_credit'])
        if load_releases:
            artist_credit_ids.add(row['release_artist_credit'])
            artist_credit_ids.add(row['track_artist_credit'])
            if load_release_groups:
                artist_credit_ids.add(row['release_group_artist_credit'])
    artists = _load_artists(conn, artist_credit_ids)
    for row in results:
        row['recording_artists'] = artists[row.pop('recording_artist_credit')]
        if load_releases:
            row['release_artists'] = artists[row.pop('release_artist_credit')]
            row['track_artists'] = artists[row.pop('track_artist_credit')]
            if load_release_groups:
                row['release_group_artists'] = artists[row.pop('release_group_artist_credit')]
    return results


def lookup_recording_metadata(conn, mbids):
    """
    Lookup MusicBrainz metadata for the specified MBIDs.
    """
    if not mbids:
        return {}
    src = schema.mb_recording.join(schema.mb_artist_credit)
    query = sql.select(
        [
            schema.mb_recording.c.gid,
            schema.mb_recording.c.name,
            schema.mb_recording.c.length,
            schema.mb_artist_credit.c.name.label('artist_name'),
        ],
        schema.mb_recording.c.gid.in_(mbids),
        from_obj=src)
    results = {}
    for row in conn.execute(query):
        result = dict(row)
        result['length'] = (result['length'] or 0) / 1000
        results[row['gid']] = result
    return results


def cluster_track_names(names):
    tokenized_names = [set([i.lower() for i in re.findall("(\w+)", n)]) for n in names]
    stats = {}
    for tokens in tokenized_names:
        for token in tokens:
            stats[token] = stats.get(token, 0) + 1
    if not stats:
        return
    top_words = set()
    max_score = max(stats.values())
    threshold = 0.7 * max_score
    for token, score in stats.items():
        if score > threshold:
            top_words.add(token)
    results = []
    for i, tokens in enumerate(tokenized_names):
        if not tokens:
            continue
        score = 1.0 * sum([float(stats[t]) / max_score for t in tokens if t in top_words]) / len(tokens)
        if score > 0.8:
            results.append((score, i))
    if not results:
        return
    results.sort(reverse=True)
    max_score = results[0][0]
    for score, i in results:
        if score > max_score * 0.8:
            yield i


def find_puid_mbids(conn, puid, min_duration, max_duration):
    """
    Find MBIDs for MusicBrainz tracks that are linked to the given PUID and
    have duration within the given range
    """
    src = schema.mb_puid
    src = src.join(schema.mb_recording_puid, schema.mb_recording_puid.c.puid == schema.mb_puid.c.id)
    src = src.join(schema.mb_recording, schema.mb_recording.c.id == schema.mb_recording_puid.c.recording)
    src = src.join(schema.mb_artist_credit, schema.mb_artist_credit.c.id == schema.mb_recording.c.artist_credit)
    condition = sql.and_(
        schema.mb_puid.c.puid == puid,
        schema.mb_recording.c.length.between(min_duration * 1000, max_duration * 1000))
    columns = [
        schema.mb_recording.c.gid,
        schema.mb_recording.c.name,
        schema.mb_artist_credit.c.name.label('artist')
    ]
    query = sql.select(columns, condition, from_obj=src).order_by(schema.mb_recording.c.id)
    rows = conn.execute(query).fetchall()
    good_group = cluster_track_names(r['name'] + ' ' + r['artist'] for r in rows)
    return [rows[i]['gid'] for i in good_group]


def resolve_mbid_redirect(conn, mbid):
    src = schema.mb_recording
    src = src.join(schema.mb_recording_gid_redirect, schema.mb_recording_gid_redirect.c.new_id == schema.mb_recording.c.id)
    condition = schema.mb_recording_gid_redirect.c.gid == mbid
    columns = [schema.mb_recording.c.gid]
    query = sql.select(columns, condition, from_obj=src)
    new_mbid = conn.execute(query).scalar()
    return new_mbid or mbid

