# Copyright (C) 2011, 2015 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging

from flask import Blueprint, render_template

from acoustid.data.stats import find_current_stats, find_daily_stats, find_lookup_stats
from acoustid.web import db

logger = logging.getLogger(__name__)

stats_page = Blueprint("stats", __name__)


def percent(x, total):
    if total == 0:
        x = 0
        total = 1
    return "%.2f" % (100.0 * x / total,)


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
        track_mbid.append(
            {
                "i": i,
                "count": count,
                "percent": percent(count, track_mbid_sum),
            }
        )
    return track_mbid


def line_chart(stats, series, tip=None, area=False):
    """Data for charts.js. Each series is (key, name, color, extra options)."""
    return {
        "labels": [item["date"].strftime("%Y-%m-%d") for item in stats],
        "series": [
            dict(
                name=name,
                color=color,
                values=[int(item.get(key) or 0) for item in stats],
                **opts,
            )
            for key, name, color, opts in series
        ],
        "tip": tip,
        "area": area,
    }


@stats_page.route("/stats")
def stats():
    title = "Statistics"
    app_db = db.get_app_db()
    stats = find_current_stats(app_db)
    basic = {
        "submissions": stats.get("submission.all", 0),
        "fingerprints": stats.get("fingerprint.all", 0),
        "tracks": stats.get("track.all", 0),
        "mbids": stats.get("mbid.all", 0),
        "contributors": stats.get("account.active", 0),
    }
    track_mbid = prepare_pie_chart_data(stats, "track.%dmbids")
    mbid_track = prepare_pie_chart_data(stats, "mbid.%dtracks")
    basic["tracks_with_mbid"] = basic["tracks"] - stats.get("track.0mbids", 0)
    coverage = basic["tracks_with_mbid"] / basic["tracks"] if basic["tracks"] else 0.0
    additions = find_daily_stats(app_db, ["track.all", "mbid.all"])
    lookups = find_lookup_stats(app_db)
    total_lookups = sum(int(d["count"] or 0) for d in lookups)
    total_hits = sum(int(d["count_hits"] or 0) for d in lookups)
    return render_template(
        "stats.html",
        title=title,
        nav="stats",
        basic=basic,
        coverage=coverage,
        track_mbid=track_mbid,
        track_mbid_max=max((t["count"] for t in track_mbid), default=0),
        mbid_track=mbid_track,
        mbid_track_max=max((t["count"] for t in mbid_track), default=0),
        last_date=additions[-1]["date"] if additions else None,
        added_tracks=sum(int(d.get("track.all") or 0) for d in additions),
        added_mbids=sum(int(d.get("mbid.all") or 0) for d in additions),
        additions_days=len(additions),
        lookups_days=len(lookups),
        avg_lookups=total_lookups / len(lookups) if lookups else 0,
        hit_rate=total_hits / total_lookups if total_lookups else 0,
        additions_chart=line_chart(
            additions,
            [
                ("track.all", "AcoustIDs", "#0145aa", {}),
                ("mbid.all", "Recordings", "#aa0000", {}),
            ],
            area=True,
        ),
        lookups_chart=line_chart(
            lookups,
            [
                ("count", "All", "#8f8c85", {"dash": "4 3", "width": 1.5}),
                ("count_hits", "Matched", "#0145aa", {}),
                ("count_nohits", "No match", "#aa0000", {}),
            ],
            tip="hit-rate",
        ),
    )
