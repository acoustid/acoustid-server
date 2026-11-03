# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""The JSON endpoint behind metadata search.

Search deliberately lives behind a separate request rather than inside a
rendered page. Two reasons, both load-bearing. The index is a single
unreplicated instance whose failures must not reach a visitor as a broken
page, and the heavy pages on this site are the ones most worth caching -- a
search result folded into a template would make those pages vary per query
and cache for nobody.
"""

from __future__ import annotations

import logging

from flask import Blueprint, current_app, jsonify, request
from flask.wrappers import Response

from acoustid.search import DEFAULT_LIMIT, search_metadata

logger = logging.getLogger(__name__)

search_page = Blueprint("search", __name__)


@search_page.route("/search.json")
def search_json() -> tuple[Response, int]:
    """Answer a metadata search.

    Returns 200 with results, or 503 with the same shape and
    `available: false` when search could not run. The 503 is deliberate: it
    makes degradation visible in access logs and to anything in front of this
    without parsing bodies, and it stops an intermediary from treating an
    empty result set as a real answer. The body is still valid JSON in that
    case, so a client only has to read `available`.
    """
    query = request.args.get("q", "")

    try:
        limit = int(request.args.get("limit", DEFAULT_LIMIT))
    except ValueError:
        # Clamped rather than rejected. A malformed limit is a client bug, and
        # failing the whole search over it helps nobody.
        limit = DEFAULT_LIMIT

    config = current_app.acoustid_config.search  # type: ignore[attr-defined]
    results = search_metadata(config, query, limit=limit)

    statsd = current_app.acoustid_script.statsd  # type: ignore[attr-defined]
    if statsd is not None:
        # Inline tags, as the rest of the project does it. The label is a fixed
        # pair of values rather than anything request-derived -- a query string
        # in a metric name would be unbounded cardinality.
        statsd.incr(
            "web.search_total,available=%s" % ("true" if results.available else "false")
        )

    response = jsonify(
        {
            "query": results.query,
            "available": results.available,
            "found": results.found,
            "results": [
                {
                    "mbid": result.mbid,
                    "name": result.name,
                    "artist": result.artist,
                    "comment": result.comment,
                    "length": result.length,
                    "popularity": result.popularity,
                    "track_count": result.track_count,
                }
                for result in results.results
            ],
        }
    )

    # Never store a search answer. A degraded response must not be cached as
    # though it were real, and a successful one is cheap to repeat.
    response.headers["Cache-Control"] = "no-store"

    return response, 200 if results.available else 503
