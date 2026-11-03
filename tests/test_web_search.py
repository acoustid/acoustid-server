# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Tests for the /search.json endpoint.

The property worth defending is that no state of the search index produces a
5xx that looks like a bug in the site. A 503 saying "search is unavailable" is
a correct answer; a 500 with a traceback is not.
"""

from typing import Any
from unittest import mock

import pytest
import requests
from flask import Flask

from tests import make_web_application


def search_config(app: Flask) -> Any:
    """The app's search config.

    Reached through getattr because make_web_application attaches it
    dynamically, which mypy cannot see on a plain Flask.
    """
    return getattr(app, "acoustid_config").search


@pytest.fixture()
def app(config_file) -> Flask:
    app = make_web_application(config_file)
    app.config["TESTING"] = True
    # The test config has no search section, so search would be switched off
    # and every test here would pass by never calling out at all.
    search_config(app).url = "http://typesense:8108"
    search_config(app).api_key = "key"
    return app


def typesense_response(payload: Any) -> mock.Mock:
    response = mock.Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


ONE_HIT = {
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


def test_returns_results(app: Flask) -> None:
    with mock.patch("requests.get", return_value=typesense_response(ONE_HIT)):
        rv = app.test_client().get("/search.json?q=bohemian+rhapsody")
    assert rv.status_code == 200
    body = rv.get_json()
    assert body["available"] is True
    assert body["found"] == 1
    assert body["results"][0]["artist"] == "Queen"
    assert body["results"][0]["mbid"] == "b1a9c0e9-d987-4042-ae91-78d6a3267d69"
    assert body["results"][0]["length"] == pytest.approx(355.106)


def test_a_dead_index_is_503_and_not_500(app: Flask) -> None:
    """The whole point of the module. 503 is an answer; 500 is a bug report."""
    with mock.patch("requests.get", side_effect=requests.Timeout("too slow")):
        rv = app.test_client().get("/search.json?q=queen")
    assert rv.status_code == 503
    body = rv.get_json()
    assert body["available"] is False
    assert body["results"] == []
    # Still JSON, so a client only has to read `available`.
    assert body["query"] == "queen"


def test_no_matches_is_200(app: Flask) -> None:
    """A search that found nothing worked, so it is not a 503."""
    with mock.patch(
        "requests.get", return_value=typesense_response({"found": 0, "hits": []})
    ):
        rv = app.test_client().get("/search.json?q=zzzz+nothing")
    assert rv.status_code == 200
    assert rv.get_json()["available"] is True
    assert rv.get_json()["results"] == []


def test_search_answers_are_never_stored(app: Flask) -> None:
    """A degraded answer cached as though real would outlive the outage."""
    with mock.patch("requests.get", return_value=typesense_response(ONE_HIT)):
        ok = app.test_client().get("/search.json?q=queen")
    with mock.patch("requests.get", side_effect=requests.Timeout()):
        degraded = app.test_client().get("/search.json?q=queen")
    assert ok.headers["Cache-Control"] == "no-store"
    assert degraded.headers["Cache-Control"] == "no-store"


def test_endpoint_does_not_touch_the_session(app: Flask) -> None:
    """No Vary: Cookie, so this never becomes a per-visitor response.

    Flask adds Vary: Cookie the moment the session is read, and the context
    processor that does that on rendered pages is why the heavy pages on this
    site are uncacheable. A JSON endpoint has no reason to inherit it.
    """
    with mock.patch("requests.get", return_value=typesense_response(ONE_HIT)):
        rv = app.test_client().get("/search.json?q=queen")
    assert "Cookie" not in rv.headers.get("Vary", "")


def test_blank_query_is_200_with_nothing(app: Flask) -> None:
    with mock.patch("requests.get") as get:
        rv = app.test_client().get("/search.json?q=")
    assert rv.status_code == 200
    assert rv.get_json()["available"] is True
    assert rv.get_json()["results"] == []
    get.assert_not_called()


def test_missing_query_parameter_does_not_fail(app: Flask) -> None:
    """No `q` at all is the state a search box starts in."""
    with mock.patch("requests.get") as get:
        rv = app.test_client().get("/search.json")
    assert rv.status_code == 200
    get.assert_not_called()


def test_garbage_limit_is_ignored_rather_than_rejected(app: Flask) -> None:
    """A malformed limit is a client bug; failing the search helps nobody."""
    with mock.patch("requests.get", return_value=typesense_response(ONE_HIT)) as get:
        rv = app.test_client().get("/search.json?q=queen&limit=banana")
    assert rv.status_code == 200
    assert get.call_args.kwargs["params"]["per_page"] == "20"


def test_limit_is_bounded(app: Flask) -> None:
    """One request must not be able to ask for the whole index."""
    with mock.patch("requests.get", return_value=typesense_response(ONE_HIT)) as get:
        app.test_client().get("/search.json?q=queen&limit=100000")
    assert get.call_args.kwargs["params"]["per_page"] == "50"


def test_unconfigured_search_is_503(app: Flask) -> None:
    """Switched off reads as unavailable, not as a server fault."""
    search_config(app).url = ""
    with mock.patch("requests.get") as get:
        rv = app.test_client().get("/search.json?q=queen")
    assert rv.status_code == 503
    assert rv.get_json()["available"] is False
    get.assert_not_called()
