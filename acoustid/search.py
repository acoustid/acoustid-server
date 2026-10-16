# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Metadata search against the Typesense index.

The index holds one document per MusicBrainz recording and is built by
acoustid/scripts/build_search_index.py. See acoustid/acoustid-server#281 for
the document model and the ranking.

Everything here is built around one rule: a search problem must never become a
visitor's problem. Search is not a primary function of the site, it runs on a
single unreplicated instance, and downtime is acceptable -- so every failure
turns into "no search right now" rather than an exception for a caller to
handle or, worse, a broken page.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

from acoustid.config import SearchConfig

logger = logging.getLogger(__name__)

# One field, matching the indexer, which puts the title, the credited artist
# and every alias of both into `text`.
#
# Querying separate name and artist fields instead is measurably worse, not a
# matter of taste: Typesense scores a document higher when all the query terms
# occur in one field, so "artist + title" -- the ordinary way people search --
# was won by whatever cover or mashup had both strings in its title. Over 20
# queries with known answers that was 10/20 hit@1 against 20/20 here. The
# aliases are what make non-Latin and misspelled input findable without a
# transliteration analyzer, and folding them into the same field is what lets
# "utada hikaru first love" reach a recording credited to 宇多田ヒカル.
QUERY_BY = "text"

# Relevance first, bucketed, then popularity. Without the popularity tiebreak
# a search for "yesterday" answers with an artist nobody has heard of at
# submission count 3, because pure text match cannot tell the difference. See
# the scoring table in #281.
SORT_BY = "_text_match(buckets: 10):desc,popularity:desc"

MAX_LIMIT = 50
DEFAULT_LIMIT = 20

# Long queries are not real queries. Typesense would cope; the point is to put
# a bound on what gets logged and on what a single request can ask for.
MAX_QUERY_LENGTH = 200


@dataclass(frozen=True)
class SearchResult:
    mbid: str
    name: str
    artist: str
    comment: str
    length_ms: int
    popularity: int
    track_count: int

    @property
    def length(self) -> float | None:
        """Duration in seconds, or None when MusicBrainz does not know it.

        The index stores 0 for unknown, because the field is not optional.
        Zero is not a duration, so it comes back out as None rather than as
        "0:00".
        """
        return self.length_ms / 1000.0 if self.length_ms else None


@dataclass(frozen=True)
class SearchResults:
    """What a search returned, including the case where it could not run.

    `available` is false when search is switched off or the index could not be
    reached. Callers render that as "search unavailable" -- distinct from a
    successful search that simply found nothing, which is `available` true with
    an empty list. Collapsing the two would tell a visitor their query has no
    matches when the truth is that nobody looked.
    """

    query: str
    results: list[SearchResult]
    found: int
    available: bool

    @classmethod
    def unavailable(cls, query: str) -> "SearchResults":
        return cls(query=query, results=[], found=0, available=False)


def parse_document(document: dict[str, Any]) -> SearchResult:
    return SearchResult(
        mbid=str(document.get("id", "")),
        name=str(document.get("name", "")),
        artist=str(document.get("artist", "")),
        comment=str(document.get("comment", "")),
        length_ms=int(document.get("length_ms") or 0),
        popularity=int(document.get("popularity") or 0),
        track_count=int(document.get("n_tracks") or 0),
    )


def search_metadata(
    config: SearchConfig, query: str, limit: int = DEFAULT_LIMIT
) -> SearchResults:
    """Search the index, or report that it could not be searched.

    Never raises. The caller is a web request, and there is no failure here
    worth turning into a 500 -- not a timeout, not a connection refused, not a
    response in a shape this code did not expect.
    """
    query = query.strip()[:MAX_QUERY_LENGTH]
    limit = max(1, min(limit, MAX_LIMIT))

    if not query:
        return SearchResults(query=query, results=[], found=0, available=True)

    if not config.enabled:
        logger.debug("Metadata search is not configured")
        return SearchResults.unavailable(query)

    try:
        response = requests.get(
            config.url.rstrip("/")
            + "/collections/"
            + config.collection
            + "/documents/search",
            headers={"X-TYPESENSE-API-KEY": config.api_key},
            params={
                "q": query,
                "query_by": QUERY_BY,
                "sort_by": SORT_BY,
                "prioritize_exact_match": "true",
                "per_page": str(limit),
                # Only the fields that are rendered. The documents are small,
                # but there is no reason to move popularity-ordered payloads
                # over the wire for columns nothing displays.
                "include_fields": "id,name,artist,comment,length_ms,"
                "popularity,n_tracks",
            },
            timeout=config.timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as error:
        # Expected in normal operation rather than exceptional: one instance,
        # no replication, and a timeout tight enough that a slow moment trips
        # it. The cause is logged but not the traceback -- the stack is always
        # these same few frames, and on a path designed to fire regularly it
        # would be pages of noise hiding the one line that says what broke.
        logger.warning("Metadata search for %r failed: %s", query, error)
        return SearchResults.unavailable(query)
    except ValueError:
        logger.warning("Metadata search for %r returned a non-JSON body", query)
        return SearchResults.unavailable(query)

    try:
        hits = payload.get("hits") or []
        results = [parse_document(hit["document"]) for hit in hits]
        found = int(payload.get("found") or 0)
    except (AttributeError, KeyError, TypeError, ValueError):
        # A response that parsed as JSON but is not the shape Typesense
        # documents. Degrading is still better than a traceback on a page.
        logger.warning(
            "Metadata search for %r returned an unexpected shape", query, exc_info=True
        )
        return SearchResults.unavailable(query)

    return SearchResults(query=query, results=results, found=found, available=True)
