# Copyright (C) 2011, 2015 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
import json
from flask import Blueprint, render_template
from acoustid.web import db
from acoustid.data.stats import (
    find_current_stats,
    find_daily_stats,
    find_lookup_stats,
)

logger = logging.getLogger(__name__)

stats_page = Blueprint('stats', __name__)


def percent(x, total):
    if total == 0:
        x = 0
        total = 1
    return '%.2f' % (100.0 * x / total,)


def prepare_pie_chart_data(stats, pattern):
    track_mbid_data = []
    track_mbid_sum = 0
    for i in range(11):
        value = stats.get(pattern % i, 0)
        if i != 0:
            track_mbid_sum += value
        track_mbid_data.append(value)
    track_mbid = []
    for i, count in enumerate(track_mbid_data):
        if i == 0:
            continue
        track_mbid.append({
            'i': i,
            'count': count,
            'percent': percent(count, track_mbid_sum),
        })
    return track_mbid


def prepare_chart_data(stats):
    for item in stats:
        item['date'] = item['date'].strftime('%Y-%m-%d')
    return stats


@stats_page.route('/stats')
def stats():
    title = 'Statistics'
    stats = find_current_stats(db.session.connection())
    basic = {
        'submissions': stats.get('submission.all', 0),
        'fingerprints': stats.get('fingerprint.all', 0),
        'tracks': stats.get('track.all', 0),
        'mbids': stats.get('mbid.all', 0),
        'contributors': stats.get('account.active', 0),
    }
    track_mbid = prepare_pie_chart_data(stats, 'track.%dmbids')
    mbid_track = prepare_pie_chart_data(stats, 'mbid.%dtracks')
    basic['tracks_with_mbid'] = basic['tracks'] - stats.get('track.0mbids', 0)
    basic['tracks_with_mbid_percent'] = percent(basic['tracks_with_mbid'], basic['tracks'])
    additions = find_daily_stats(db.session.connection(), ['track.all', 'mbid.all'])
    lookups = find_lookup_stats(db.session.connection())
    return render_template('stats.html', title=title, basic=basic,
        track_mbid=track_mbid, mbid_track=mbid_track,
        additions_json=json.dumps(prepare_chart_data(additions)),
        lookups_json=json.dumps(prepare_chart_data(lookups)))
