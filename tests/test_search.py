# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Tests for the metadata search client.

The contract under test is narrow and the whole point of the module: no input
and no response makes this raise. A traceback escaping here becomes a broken
page, and the index it talks to is a single unreplicated instance that is
expected to be unreachable sometimes.
"""

from typing import Any
from unittest import mock

import pytest
import requests

from acoustid.config import SearchConfig
from acoustid.search import MAX_LIMIT, MAX_QUERY_LENGTH, SearchResults, search_metadata


def make_config(**kwargs: Any) -> SearchConfig:
    config = SearchConfig()
    config.url = "http://typesense:8108"
    config.api_key = "key"
    config.collection = "mb_recordings"
    for name, value in kwargs.items():
        setattr(config, name, value)
    return config


def typesense_response(payload: Any, status: int = 200) -> mock.Mock:
    response = mock.Mock()
    response.json.return_value = payload
    response.status_code = status
    response.raise_for_status.return_value = None
    return response


ONE_HIT: dict[str, Any] = {
    "found": 1,
    "hits": [
        {
            "document": {
                "id": "b1a9c0e9-d987-4042-ae91-78d6a3267d69",
                "name": "Bohemian Rhapsody",
                "artist": "Queen",
                "comment": "",
                "length_ms": 355106,
                "popularity": 19718,
                "n_tracks": 40,
            }
        }
    ],
}


DOCUMENT: dict[str, Any] = ONE_HIT["hits"][0]["document"]


def test_parses_a_hit() -> None:
    with mock.patch("requests.get", return_value=typesense_response(ONE_HIT)):
        results = search_metadata(make_config(), "bohemian rhapsody")
    assert results.available is True
    assert results.found == 1
    assert len(results.results) == 1
    result = results.results[0]
    assert result.name == "Bohemian Rhapsody"
    assert result.artist == "Queen"
    assert result.popularity == 19718
    assert result.track_count == 40
    assert result.length == pytest.approx(355.106)


def test_no_matches_is_available_not_unavailable() -> None:
    """An empty result set and a failed search must not look the same.

    Collapsing them tells a visitor their query has no matches when the truth
    is that nobody looked, which is the more misleading of the two answers.
    """
    with mock.patch(
        "requests.get", return_value=typesense_response({"found": 0, "hits": []})
    ):
        results = search_metadata(make_config(), "zzzzz no such recording")
    assert results.available is True
    assert results.results == []


@pytest.mark.parametrize(
    "error",
    [
        requests.ConnectionError("refused"),
        requests.Timeout("too slow"),
        requests.HTTPError("500 from typesense"),
    ],
)
def test_transport_failures_degrade(error: Exception) -> None:
    """Every way the index can be unreachable ends as "no search right now"."""
    with mock.patch("requests.get", side_effect=error):
        results = search_metadata(make_config(), "queen")
    assert results.available is False
    assert results.results == []


def test_non_json_body_degrades() -> None:
    """A proxy error page in place of a response must not raise."""
    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.side_effect = ValueError("not json")
    with mock.patch("requests.get", return_value=response):
        results = search_metadata(make_config(), "queen")
    assert results.available is False


@pytest.mark.parametrize(
    "payload",
    [
        {"hits": [{"no_document_key": {}}]},
        {"hits": "not a list"},
        {"hits": [{"document": "not a dict"}]},
        "not an object at all",
        None,
    ],
)
def test_unexpected_shapes_degrade(payload: Any) -> None:
    """Valid JSON in the wrong shape is still not a reason to raise."""
    with mock.patch("requests.get", return_value=typesense_response(payload)):
        results = search_metadata(make_config(), "queen")
    assert results.available is False


def test_search_is_skipped_when_not_configured() -> None:
    """With no URL or key there is nothing to ask, and nothing to raise."""
    config = make_config(url="", api_key="")
    with mock.patch("requests.get") as get:
        results = search_metadata(config, "queen")
    assert results.available is False
    get.assert_not_called()


def test_blank_query_does_not_reach_the_index() -> None:
    """An empty box is not a failed search, and not a request either."""
    with mock.patch("requests.get") as get:
        results = search_metadata(make_config(), "   ")
    assert results.available is True
    assert results.results == []
    get.assert_not_called()


def test_limit_is_clamped_to_the_maximum() -> None:
    """One request must not be able to ask for the whole index."""
    with mock.patch("requests.get", return_value=typesense_response(ONE_HIT)) as get:
        search_metadata(make_config(), "queen", limit=10_000)
    assert get.call_args.kwargs["params"]["per_page"] == str(MAX_LIMIT)


def test_limit_below_one_is_raised_to_one() -> None:
    with mock.patch("requests.get", return_value=typesense_response(ONE_HIT)) as get:
        search_metadata(make_config(), "queen", limit=0)
    assert get.call_args.kwargs["params"]["per_page"] == "1"


def test_long_query_is_truncated() -> None:
    """Bounds what a single request can send, and what gets logged."""
    with mock.patch("requests.get", return_value=typesense_response(ONE_HIT)) as get:
        search_metadata(make_config(), "q" * 5000)
    assert len(get.call_args.kwargs["params"]["q"]) == MAX_QUERY_LENGTH


def test_configured_timeout_is_passed_through() -> None:
    """The timeout is the whole reason a visitor is not left waiting."""
    with mock.patch("requests.get", return_value=typesense_response(ONE_HIT)) as get:
        search_metadata(make_config(timeout=0.25), "queen")
    assert get.call_args.kwargs["timeout"] == 0.25


def test_unknown_length_comes_back_as_none() -> None:
    """The index stores 0 for unknown, and 0 is not a duration."""
    payload = {
        "found": 1,
        "hits": [{"document": dict(DOCUMENT, length_ms=0)}],
    }
    with mock.patch("requests.get", return_value=typesense_response(payload)):
        results = search_metadata(make_config(), "queen")
    assert results.results[0].length is None


def test_queries_one_combined_field() -> None:
    """Pins the configuration, because the obvious alternative is much worse.

    Typesense scores a document higher when every query term occurs in a
    single field, so querying separate name and artist fields hands every
    "artist + title" search to whichever cover or mashup put both strings in
    its title. Measured over 20 queries with known answers against real
    documents: 10/20 hit@1 that way, 20/20 against the combined field the
    indexer builds. Reintroducing per-field weights would silently undo it.
    """
    with mock.patch("requests.get", return_value=typesense_response(ONE_HIT)) as get:
        search_metadata(make_config(), "queen bohemian rhapsody")
    params = get.call_args.kwargs["params"]
    assert params["query_by"] == "text"
    assert "query_by_weights" not in params
    assert params["sort_by"] == "_text_match(buckets: 10):desc,popularity:desc"


def test_unavailable_helper_keeps_the_query() -> None:
    """The caller echoes the query back, so it has to survive the failure."""
    assert SearchResults.unavailable("queen").query == "queen"
