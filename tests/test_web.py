import datetime
import json
import logging
from typing import Any
from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest
from flask import Flask
from itsdangerous import URLSafeSerializer
from rauth import OAuth2Service
from sqlalchemy import sql

from acoustid.web import db
from acoustid.web.views import general
from acoustid.web.views.user import LoginError, validate_openid_identifier
from tests import make_web_application


@pytest.fixture()
def app(config_file) -> Flask:
    app = make_web_application(config_file)
    app.config["TESTING"] = True
    return app


def test_home_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/")
    assert rv.status_code == 200
    assert "Open source audio identification" in rv.text


def test_docs_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/docs")
    assert rv.status_code == 200
    assert "Documentation" in rv.text


FAKE_RELEASE = {
    "name": "Chromaprint 1.6.1",
    "published_at": "2026-07-27T10:00:00Z",
    "assets": [
        {
            "name": "chromaprint-1.6.1-linux-x86_64.tar.gz",
            "browser_download_url": "https://example.com/chromaprint.tar.gz",
            "size": 1234567,
        }
    ],
}


@pytest.fixture()
def latest_release():
    with mock.patch.object(general, "get_latest_chromaprint_release") as m:
        yield m


def test_chromaprint_page(app: Flask, latest_release) -> None:
    latest_release.return_value = FAKE_RELEASE
    client = app.test_client()

    rv = client.get("/chromaprint")
    assert rv.status_code == 200
    assert "Download" in rv.text
    # The name has "Chromaprint" stripped and the timestamp is cut to a date,
    # so assert the rendered forms rather than substrings of the raw values.
    assert "1.6.1 (2026-07-27)" in rv.text
    assert "2026-07-27T" not in rv.text
    assert "Chromaprint 1.6.1" not in rv.text
    assert "chromaprint-1.6.1-linux-x86_64.tar.gz" in rv.text
    assert "https://example.com/chromaprint.tar.gz" in rv.text
    assert "1.2 MB" in rv.text


def test_chromaprint_page_without_a_release(app: Flask, latest_release) -> None:
    latest_release.return_value = None
    client = app.test_client()

    rv = client.get("/chromaprint")
    assert rv.status_code == 200
    assert "Download" not in rv.text


def test_latest_chromaprint_release_is_the_newest_one(fake_redis) -> None:
    older = dict(FAKE_RELEASE, name="Chromaprint 1.6.0")
    with mock.patch.object(general.requests, "get") as get:
        get.return_value.json.return_value = [FAKE_RELEASE, older]

        assert general.get_latest_chromaprint_release() == FAKE_RELEASE


def test_latest_chromaprint_release_when_there_are_none(fake_redis) -> None:
    with mock.patch.object(general.requests, "get") as get:
        get.return_value.json.return_value = []

        assert general.get_latest_chromaprint_release() is None


def test_faq_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/faq")
    assert rv.status_code == 200


def test_webservice_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/webservice")
    assert rv.status_code == 200
    assert "/v2/lookup" in rv.text
    assert "/v2/submit" in rv.text


def test_stats_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/stats")
    assert rv.status_code == 200
    assert "Daily additions" in rv.text
    assert "Searches per day" in rv.text


def test_login_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/login")
    assert rv.status_code == 200
    assert 'name="login" value="musicbrainz"' in rv.text
    assert 'name="login" value="google"' in rv.text


def test_contact_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/contact")
    assert rv.status_code == 200
    assert "info@acoustid.org" in rv.text


def test_track_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/track/eb31d1c3-950e-468b-9e36-e46fa75b1291")
    assert rv.status_code == 200
    assert "b81f83ee-4da4-11e0-9ed8-0025225356f3" in rv.text
    assert "Custom Track 1" in rv.text
    assert "Custom Track 2" in rv.text
    assert not db.session.registry.has()

    rv = client.get("/track/eb31d1c3-950e-468b-9e36-e46fa75b1291?metadata=raw")
    assert rv.status_code == 200
    assert rv.data.count(b"Custom Track") == 2
    assert rv.data.count(b"Custom Artist") == 2


def test_track_page_show_disabled(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/track/eb31d1c3-950e-468b-9e36-e46fa75b1291")
    assert "54b7b412-fc69-4fc7-8c96-17800eda3a98" not in rv.text
    assert "Show 1 disabled recording" in rv.text
    assert rv.status_code == 200

    rv = client.get("/track/eb31d1c3-950e-468b-9e36-e46fa75b1291?disabled=1")
    assert "54b7b412-fc69-4fc7-8c96-17800eda3a98" in rv.text
    assert "Show 1 disabled recording" not in rv.text
    assert rv.status_code == 200


@pytest.mark.parametrize(
    "identifier",
    [
        "",
        "   ",
        "hueypeard@gmail.com",
        "ade.bateman@outlook.com",
        "doubleuotb",
        "dybgm665953",
        "http://localhost",
        "[bad",
        "http://[bad",
        "]",
    ],
)
def test_validate_openid_identifier_rejects(identifier: str) -> None:
    with pytest.raises(LoginError):
        validate_openid_identifier(identifier)


@pytest.mark.parametrize(
    "identifier",
    [
        "https://example.com/openid",
        "example.com/openid",
        "https://musicbrainz.org/user/someone",
    ],
)
def test_validate_openid_identifier_accepts(identifier: str) -> None:
    assert validate_openid_identifier(identifier) == identifier


def spy_on_token_exchange(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every call to an OAuth2 token endpoint, and make it fail.

    The state check is only worth anything if it happens *before* we spend the
    authorization code, so the tests below assert on ordering rather than only
    on the error the user ends up seeing. They record instead of asserting
    because the login routes catch every exception -- an AssertionError raised
    in here would be swallowed and turned into a redirect, and the test would
    pass whether or not the code had already been exchanged.
    """
    calls: list[str] = []

    def record(self: OAuth2Service, *args: object, **kwargs: object) -> None:
        calls.append(self.name)
        raise RuntimeError("the token endpoint must not be contacted")

    monkeypatch.setattr(OAuth2Service, "get_raw_access_token", record)
    monkeypatch.setattr(OAuth2Service, "get_auth_session", record)
    return calls


def test_google_login_sends_state(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/login/google")
    assert rv.status_code == 302

    query = parse_qs(urlparse(rv.headers["Location"]).query)
    with client.session_transaction() as flask_session:
        token = flask_session["google_login_token"]

    assert token
    assert query["state"] == [token]


def test_musicbrainz_login_sends_state(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/login/musicbrainz")
    assert rv.status_code == 302

    query = parse_qs(urlparse(rv.headers["Location"]).query)
    with client.session_transaction() as flask_session:
        token = flask_session["mb_login_token"]

    assert token
    # MusicBrainz wraps the token in a signed blob alongside the return URL.
    state = URLSafeSerializer(app.config["SECRET_KEY"]).loads(query["state"][0])
    assert state["token"] == token


@pytest.mark.parametrize(
    "state",
    [
        None,  # no state parameter at all -- the flaw this fixes
        "",
        "not-the-token-we-issued",
        "— not even ascii",
    ],
)
def test_google_login_rejects_bad_state(
    app: Flask, monkeypatch: pytest.MonkeyPatch, state: str | None
) -> None:
    calls = spy_on_token_exchange(monkeypatch)
    client = app.test_client()

    with client.session_transaction() as flask_session:
        flask_session["google_login_token"] = "the-token-we-issued"

    args = {"code": "an-authorization-code"}
    if state is not None:
        args["state"] = state

    rv = client.get("/login/google", query_string=args)

    assert rv.status_code == 302
    assert urlparse(rv.headers["Location"]).path == "/login"
    assert calls == []  # rejected before the code was spent
    with client.session_transaction() as flask_session:
        assert "id" not in flask_session


def test_google_login_rejects_state_with_no_session_token(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = spy_on_token_exchange(monkeypatch)
    client = app.test_client()

    rv = client.get(
        "/login/google",
        query_string={"code": "an-authorization-code", "state": "anything"},
    )

    assert rv.status_code == 302
    assert urlparse(rv.headers["Location"]).path == "/login"
    assert calls == []
    with client.session_transaction() as flask_session:
        assert "id" not in flask_session


def test_google_login_state_is_single_use(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A callback URL out of somebody's history must not work twice."""
    calls = spy_on_token_exchange(monkeypatch)
    client = app.test_client()

    with client.session_transaction() as flask_session:
        flask_session["google_login_token"] = "the-token-we-issued"

    args = {"code": "an-authorization-code", "state": "the-token-we-issued"}

    # The first attempt matches, gets past the check, and reaches the token
    # endpoint -- which is as far as it should get here.
    client.get("/login/google", query_string=args)
    assert calls == ["google"]

    with client.session_transaction() as flask_session:
        assert "google_login_token" not in flask_session

    # The second finds nothing left to check against and never gets that far.
    rv = client.get("/login/google", query_string=args)
    assert rv.status_code == 302
    assert urlparse(rv.headers["Location"]).path == "/login"
    assert calls == ["google"]


def test_musicbrainz_login_rejects_bad_state(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = spy_on_token_exchange(monkeypatch)
    client = app.test_client()

    with client.session_transaction() as flask_session:
        flask_session["mb_login_token"] = "the-token-we-issued"

    state = URLSafeSerializer(app.config["SECRET_KEY"]).dumps(
        {"return_url": None, "token": "not-the-token-we-issued"}
    )
    rv = client.get(
        "/login/musicbrainz",
        query_string={"code": "an-authorization-code", "state": state},
    )

    assert rv.status_code == 302
    assert urlparse(rv.headers["Location"]).path == "/login"
    assert calls == []


def test_edit_application_page(app: Flask) -> None:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = 1

    rv = client.get("/application/1/edit")
    assert rv.status_code == 200
    assert 'value="App 1"' in rv.text


def test_edit_application_rejects_missing_name(app: Flask) -> None:
    """A validation error must re-render the form, not fail the request.

    The form values were only prepared on the GET path, so submitting an
    invalid form fell through to the template with them unbound.
    """
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = 1

    rv = client.post(
        "/application/1/edit",
        data={"submit": "1", "name": "", "version": "0.2", "email": "", "website": ""},
    )

    assert rv.status_code == 200
    assert "Missing application name" in rv.text
    # The version the user typed survives, rather than being reset to the
    # stored value.
    assert 'value="0.2"' in rv.text


def test_edit_application_rejects_invalid_email(app: Flask) -> None:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = 1

    rv = client.post(
        "/application/1/edit",
        data={
            "submit": "1",
            "name": "App 1",
            "version": "0.1",
            "email": "not-an-email",
            "website": "",
        },
    )

    assert rv.status_code == 200
    assert "Invalid email address" in rv.text
    assert 'value="not-an-email"' in rv.text


def test_new_application_page_does_not_call_email_optional(app: Flask) -> None:
    """The form must not offer the email as optional when it is not."""
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = 1

    rv = client.get("/new-application")
    assert rv.status_code == 200
    assert "Contact email" in rv.text
    assert "Contact email (optional)" not in rv.text
    # The website really is optional, and should still say so.
    assert "Website (optional)" in rv.text


def test_new_application_requires_email(app: Flask) -> None:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = 1

    rv = client.post(
        "/new-application",
        data={"submit": "1", "name": "App 3", "version": "0.1", "email": ""},
    )

    assert rv.status_code == 200
    assert "Missing email address" in rv.text


def test_edit_application_requires_email(app: Flask) -> None:
    """Clearing the email must be rejected, as it is on registration."""
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = 1

    rv = client.post(
        "/application/1/edit",
        data={"submit": "1", "name": "App 1", "version": "0.1", "email": ""},
    )

    assert rv.status_code == 200
    assert "Missing email address" in rv.text


def test_edit_application_page_does_not_call_email_optional(app: Flask) -> None:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = 1

    rv = client.get("/application/1/edit")
    assert rv.status_code == 200
    assert "Contact email" in rv.text
    assert "Contact email (optional)" not in rv.text
    assert "Website (optional)" in rv.text


def test_maintenance_banner_hidden_by_default(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/")
    assert rv.status_code == 200
    assert "read-only mode for maintenance" not in rv.text


def test_maintenance_banner_links_to_status_page(app: Flask) -> None:
    website = app.acoustid_config.website  # type: ignore[attr-defined]
    website.maintenance = True
    try:
        client = app.test_client()

        rv = client.get("/")
        assert rv.status_code == 200
        assert "read-only mode for maintenance" in rv.text
        assert "https://status.acoustid.org/" in rv.text
    finally:
        website.maintenance = False


class FakeRedis:
    """A redis stand-in that can be told to fail, because the real one does."""

    def __init__(self, fail=False):
        self.store = {}
        self.fail = fail
        self.writes = 0

    def get(self, key):
        if self.fail:
            raise Exception("upstream failure")
        return self.store.get(key)

    def setex(self, key, ttl, value):
        self.writes += 1
        if self.fail:
            raise Exception("upstream failure")
        # bytes, because that is what redis-py hands back and the code has to
        # cope with it
        self.store[key] = value.encode() if isinstance(value, str) else value

    def set(self, key, value, nx=False, ex=None):
        if self.fail:
            raise Exception("upstream failure")
        if nx and key in self.store:
            return None
        self.store[key] = value.encode() if isinstance(value, str) else value
        return True

    def delete(self, key):
        if self.fail:
            raise Exception("upstream failure")
        self.store.pop(key, None)


@pytest.fixture()
def fake_redis():
    redis = FakeRedis()
    with mock.patch.object(db, "get_redis", return_value=redis):
        yield redis


@pytest.fixture()
def github():
    with mock.patch.object(general, "_fetch_latest_chromaprint_release") as m:
        m.return_value = FAKE_RELEASE
        yield m


def test_chromaprint_release_is_cached_in_redis(fake_redis, github) -> None:
    assert general.get_latest_chromaprint_release() == FAKE_RELEASE
    assert general.get_latest_chromaprint_release() == FAKE_RELEASE
    # the second call is served from redis rather than from GitHub, which is
    # the whole point: the call is unauthenticated and rate limited per IP
    assert github.call_count == 1


def test_chromaprint_release_survives_github_being_down(fake_redis, github) -> None:
    github.side_effect = RuntimeError("403 rate limited")
    assert general.get_latest_chromaprint_release() is None


def test_chromaprint_page_renders_when_github_is_down(
    app: Flask, fake_redis, github
) -> None:
    """The version is an ornament; GitHub being unreachable must not 500."""
    github.side_effect = RuntimeError("403 rate limited")
    rv = app.test_client().get("/chromaprint")
    assert rv.status_code == 200


def test_chromaprint_serves_a_stale_release_when_github_is_down(
    fake_redis, github
) -> None:
    assert general.get_latest_chromaprint_release() == FAKE_RELEASE

    # age the cached entry past its freshness window
    cached = json.loads(fake_redis.store[general.CHROMAPRINT_RELEASE_CACHE_KEY])
    cached["fetched_at"] = (
        datetime.datetime.now(datetime.timezone.utc)
        - general.CHROMAPRINT_RELEASE_TTL
        - datetime.timedelta(minutes=1)
    ).isoformat()
    fake_redis.store[general.CHROMAPRINT_RELEASE_CACHE_KEY] = json.dumps(cached)

    github.side_effect = RuntimeError("403 rate limited")
    assert general.get_latest_chromaprint_release() == FAKE_RELEASE
    assert github.call_count == 2


def test_chromaprint_page_renders_when_redis_is_down(app: Flask, github) -> None:
    """Caching in redis must not swap a GitHub dependency for a redis one --
    the shards sit behind a proxy that blips."""
    redis = FakeRedis(fail=True)
    with mock.patch.object(db, "get_redis", return_value=redis):
        assert general.get_latest_chromaprint_release() == FAKE_RELEASE
        rv = app.test_client().get("/chromaprint")
    assert rv.status_code == 200


def test_chromaprint_survives_redis_and_github_both_being_down(app: Flask) -> None:
    redis = FakeRedis(fail=True)
    with mock.patch.object(db, "get_redis", return_value=redis):
        with mock.patch.object(general, "_fetch_latest_chromaprint_release") as m:
            m.side_effect = RuntimeError("403 rate limited")
            assert general.get_latest_chromaprint_release() is None
            rv = app.test_client().get("/chromaprint")
    assert rv.status_code == 200


def test_chromaprint_ignores_an_unreadable_cache_entry(fake_redis, github) -> None:
    fake_redis.store[general.CHROMAPRINT_RELEASE_CACHE_KEY] = b"not json"
    assert general.get_latest_chromaprint_release() == FAKE_RELEASE


def cached_entry(fake_redis):
    return json.loads(fake_redis.store[general.CHROMAPRINT_RELEASE_CACHE_KEY])


def age_out_cache(fake_redis, entry=None):
    """Push the cached entry past its freshness window."""
    entry = entry or cached_entry(fake_redis)
    entry["fetched_at"] = (
        datetime.datetime.now(datetime.timezone.utc)
        - general.CHROMAPRINT_RELEASE_TTL
        - datetime.timedelta(minutes=1)
    ).isoformat()
    fake_redis.store[general.CHROMAPRINT_RELEASE_CACHE_KEY] = json.dumps(entry).encode()


def test_chromaprint_ignores_a_cache_entry_with_a_naive_timestamp(
    fake_redis, github
) -> None:
    """fromisoformat takes a naive timestamp happily, and subtracting one from
    an aware now() raises -- which on this page means the 500 this all exists
    to prevent."""
    fake_redis.store[general.CHROMAPRINT_RELEASE_CACHE_KEY] = json.dumps(
        {"fetched_at": "2026-09-29T12:00:00", "release": FAKE_RELEASE}
    ).encode()

    assert general.get_latest_chromaprint_release() == FAKE_RELEASE


def test_chromaprint_page_renders_with_a_naive_cache_timestamp(
    app: Flask, fake_redis, github
) -> None:
    fake_redis.store[general.CHROMAPRINT_RELEASE_CACHE_KEY] = json.dumps(
        {"fetched_at": "2026-09-29T12:00:00", "release": FAKE_RELEASE}
    ).encode()

    assert app.test_client().get("/chromaprint").status_code == 200


def test_chromaprint_keeps_the_last_release_when_github_reports_none(
    fake_redis, github
) -> None:
    """A 200 saying "no releases" must not be more destructive than an error.

    Everywhere else a bad answer keeps what we have; an empty list is more
    likely to be transient than to mean the downloads went away.
    """
    assert general.get_latest_chromaprint_release() == FAKE_RELEASE
    age_out_cache(fake_redis)

    github.return_value = None
    assert general.get_latest_chromaprint_release() == FAKE_RELEASE
    assert cached_entry(fake_redis)["release"] == FAKE_RELEASE


def test_chromaprint_stops_calling_github_after_a_failure(fake_redis, github) -> None:
    """Caching removed the 500s; the backoff is what removes the calls. Without
    it, a rate-limited GitHub still means one request per page view."""
    github.side_effect = RuntimeError("403 rate limited")

    for _ in range(5):
        assert general.get_latest_chromaprint_release() is None

    assert github.call_count == 1


def test_chromaprint_backoff_serves_the_stale_release(fake_redis, github) -> None:
    assert general.get_latest_chromaprint_release() == FAKE_RELEASE
    age_out_cache(fake_redis)
    github.side_effect = RuntimeError("403 rate limited")

    assert general.get_latest_chromaprint_release() == FAKE_RELEASE
    assert general.get_latest_chromaprint_release() == FAKE_RELEASE
    # one call to populate the cache and one that failed; the views after the
    # failure are answered from the cache rather than from GitHub
    assert github.call_count == 2


@pytest.fixture()
def track_fingerprints(app: Flask):
    """Three fingerprints on track 1: two of the same audio and one unrelated."""
    from acoustid import tables as schema
    from acoustid.data.fingerprint import insert_fingerprint
    from tests import TEST_1A_FP_RAW, TEST_1B_FP_RAW, TEST_2_FP_RAW

    script = app.acoustid_script  # type: ignore
    ids = []
    with script.context() as ctx:
        for fp, length in (
            (TEST_1A_FP_RAW, 260),
            (TEST_1B_FP_RAW, 261),
            (TEST_2_FP_RAW, 320),
        ):
            ids.append(
                insert_fingerprint(
                    ctx.db.get_fingerprint_db(),
                    ctx.db.get_ingest_db(),
                    {"fingerprint": fp, "length": length, "track_id": 1},
                )
            )
        ctx.db.session.commit()
    yield ids
    with script.context() as ctx:
        ctx.db.get_fingerprint_db().execute(
            schema.fingerprint.delete().where(schema.fingerprint.c.id.in_(ids))
        )
        ctx.db.session.commit()


def test_track_page_fingerprints(app: Flask, track_fingerprints) -> None:
    client = app.test_client()

    rv = client.get("/track/eb31d1c3-950e-468b-9e36-e46fa75b1291")
    assert rv.status_code == 200
    a, b, c = track_fingerprints
    assert 'class="fp fp-thumb"' in rv.text
    assert "How similar are they?" in rv.text
    assert "/fingerprint/%d/compare/%d" % (a, b) in rv.text


def test_track_page_draws_only_the_most_submitted_fingerprints(
    app: Flask, track_fingerprints
) -> None:
    from acoustid import tables as schema
    from acoustid.web.views import metadata

    a, b, c = track_fingerprints
    with app.acoustid_script.context() as ctx:  # type: ignore
        ctx.db.get_fingerprint_db().execute(
            schema.fingerprint.update()
            .where(schema.fingerprint.c.id == c)
            .values(submission_count=5)
        )
        ctx.db.session.commit()

    with mock.patch.object(metadata, "MAX_FINGERPRINT_THUMBNAILS", 2):
        rv = app.test_client().get("/track/eb31d1c3-950e-468b-9e36-e46fa75b1291")
    assert rv.status_code == 200
    # Above the limit there are still drawings, of the most submitted ones.
    assert rv.text.count('class="fp fp-thumb"') == 2
    assert "Drawn for the 2 most submitted" in rv.text
    # a and b have one submission each, so b, the later one, is left out.
    rows = {
        fp: next(r for r in rv.text.split("<tr") if '/fingerprint/%d">' % fp in r)
        for fp in (a, b, c)
    }
    assert "fp-thumb" in rows[a] and "fp-thumb" in rows[c]
    assert "fp-thumb" not in rows[b]


def test_track_page_lists_most_submitted_fingerprints_first(
    app: Flask, track_fingerprints
) -> None:
    from acoustid import tables as schema

    a, b, c = track_fingerprints
    with app.acoustid_script.context() as ctx:  # type: ignore
        ctx.db.get_fingerprint_db().execute(
            schema.fingerprint.update()
            .where(schema.fingerprint.c.id == c)
            .values(submission_count=5)
        )
        ctx.db.session.commit()

    rv = app.test_client().get("/track/eb31d1c3-950e-468b-9e36-e46fa75b1291")
    row = '/fingerprint/%d">%d</a>'
    assert rv.text.index(row % (c, c)) < rv.text.index(row % (a, a))
    assert rv.text.index(row % (a, a)) < rv.text.index(row % (b, b))


def test_fingerprint_page(app: Flask, track_fingerprints) -> None:
    client = app.test_client()
    a, b, c = track_fingerprints

    rv = client.get("/fingerprint/%d" % a)
    assert rv.status_code == 200
    assert "#%d" % a in rv.text
    # The other fingerprint of the same audio ranks first.
    assert rv.text.index("#%d" % b) < rv.text.index("#%d" % c)
    assert "Same recording" in rv.text


def test_compare_fingerprints_page(app: Flask, track_fingerprints) -> None:
    client = app.test_client()
    a, b, c = track_fingerprints

    rv = client.get("/fingerprint/%d/compare/%d" % (a, b))
    assert rv.status_code == 200
    assert "#%d vs #%d" % (a, b) in rv.text
    assert "matcher score" in rv.text

    rv = client.get("/fingerprint/%d/compare/999999" % a)
    assert rv.status_code == 404


def test_fingerprint_page_large_track(app: Flask, track_fingerprints) -> None:
    from acoustid.web.views import metadata

    client = app.test_client()
    a, b, c = track_fingerprints

    with mock.patch.object(metadata, "MAX_RANKED_FINGERPRINTS", 2):
        rv = client.get("/fingerprint/%d" % a)
    assert rv.status_code == 200
    assert "most submitted of 3 fingerprints" in rv.text
    assert "Same recording" not in rv.text


def test_not_found_pages(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/no-such-page")
    assert rv.status_code == 404
    assert "There is no page at this address." in rv.text

    rv = client.get("/track/00000000-0000-0000-0000-000000000000")
    assert rv.status_code == 404
    assert "There is no track with ID 00000000-0000-0000-0000-000000000000" in rv.text

    rv = client.get("/fingerprint/999999")
    assert rv.status_code == 404
    assert "There is no fingerprint #999999" in rv.text

    rv = client.get("/mbid/00000000-0000-0000-0000-000000000000")
    assert rv.status_code == 404
    assert "There is no MusicBrainz recording" in rv.text


@pytest.fixture()
def moderator(app: Flask):
    """Account 1, signed in with MusicBrainz, which makes it a moderator."""
    from acoustid import tables as schema

    script = app.acoustid_script  # type: ignore
    with script.context() as ctx:
        ctx.db.get_app_db().execute(
            schema.account.update()
            .where(schema.account.c.id == 1)
            .values(mbuser="moderator")
        )
        ctx.db.session.commit()
    yield 1
    with script.context() as ctx:
        ctx.db.get_app_db().execute(
            schema.account.update().where(schema.account.c.id == 1).values(mbuser=None)
        )
        ctx.db.get_fingerprint_db().execute(
            schema.track_mbid.update()
            .where(schema.track_mbid.c.mbid == "b81f83ee-4da4-11e0-9ed8-0025225356f3")
            .values(disabled=False)
        )
        ctx.db.get_ingest_db().execute(schema.track_mbid_change.delete())
        ctx.db.session.commit()


TOGGLE_URL = (
    "/edit/toggle-track-mbid?track_gid=eb31d1c3-950e-468b-9e36-e46fa75b1291"
    "&mbid=b81f83ee-4da4-11e0-9ed8-0025225356f3&state=1"
)


def test_toggle_track_mbid_requires_musicbrainz_account(app: Flask) -> None:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = 1

    rv = client.get(TOGGLE_URL)
    assert rv.status_code == 200
    assert "MusicBrainz account required" in rv.text


def test_toggle_track_mbid(app: Flask, moderator: int) -> None:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = moderator

    rv = client.get(TOGGLE_URL)
    assert rv.status_code == 200
    assert "Unlink this recording?" in rv.text
    assert "b81f83ee-4da4-11e0-9ed8-0025225356f3" in rv.text

    rv = client.post(
        "/edit/toggle-track-mbid",
        data={
            "track_id": "1",
            "mbid": "b81f83ee-4da4-11e0-9ed8-0025225356f3",
            "state": "1",
            "note": "wrong version",
            "submit": "1",
        },
    )
    assert rv.status_code == 302

    rv = client.get("/track/eb31d1c3-950e-468b-9e36-e46fa75b1291")
    assert "Show 2 disabled recordings" in rv.text


def test_account_page(app: Flask) -> None:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = 1

    rv = client.get("/api-key")
    assert rv.status_code == 200
    assert "user1key" in rv.text
    assert "Replace my API key" in rv.text
    assert 'href="/my-applications"' in rv.text


def test_account_link_in_header(app: Flask) -> None:
    client = app.test_client()
    assert "Your account" not in client.get("/").text

    with client.session_transaction() as flask_session:
        flask_session["id"] = 1
    assert "Your account" in client.get("/").text


def test_about_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/about")
    assert rv.status_code == 200
    assert "History" in rv.text
    assert 'class="timeline"' in rv.text
    # The test database has no stats, so the current numbers are left out.
    assert "Today the database holds" not in rv.text


@pytest.fixture(autouse=True)
def isolated_stats_cache():
    """Every test gets its own cache, so cached numbers never leak between them."""
    from acoustid.web import stats_cache

    with mock.patch.object(stats_cache.db, "get_redis", return_value=FakeRedis()):
        yield


def test_stats_are_cached(app: Flask) -> None:
    from acoustid.web import stats_cache

    with app.test_request_context():
        with mock.patch.object(
            stats_cache, "find_current_stats", return_value={"fingerprint.all": 5}
        ) as find:
            assert stats_cache.get_current_stats() == {"fingerprint.all": 5}
            assert stats_cache.get_current_stats() == {"fingerprint.all": 5}
        assert find.call_count == 1


def test_stats_work_without_redis(app: Flask) -> None:
    from acoustid.web import stats_cache

    with app.test_request_context():
        with (
            mock.patch.object(
                stats_cache.db, "get_redis", return_value=FakeRedis(fail=True)
            ),
            mock.patch.object(
                stats_cache, "find_current_stats", return_value={"fingerprint.all": 5}
            ) as find,
        ):
            assert stats_cache.get_current_stats() == {"fingerprint.all": 5}
            assert stats_cache.get_current_stats() == {"fingerprint.all": 5}
        assert find.call_count == 2

    rv = app.test_client().get("/")
    assert rv.status_code == 200


def test_home_page_falls_back_to_a_known_song(app: Flask) -> None:
    # The test database has no fingerprint linked to a recording.
    rv = app.test_client().get("/")
    assert rv.status_code == 200
    assert "Lower Your Eyelids to Die With the Sun" in rv.text


def test_home_page_song_is_picked_once_per_hour(app: Flask) -> None:
    from acoustid.web import featured_song

    song = {
        "track": "eb31d1c3-950e-468b-9e36-e46fa75b1291",
        "name": "Random Song",
        "artist": "Random Artist",
        "fingerprint": [1, 2, 3],
    }
    client = app.test_client()
    with mock.patch.object(
        featured_song, "pick_random_song", return_value=song
    ) as pick:
        assert "Random Song" in client.get("/").text
        assert "Random Song" in client.get("/").text
    assert pick.call_count == 1


def test_home_page_renders_without_the_database(app: Flask) -> None:
    from acoustid.web import featured_song, stats_cache

    with (
        mock.patch.object(
            stats_cache, "find_current_stats", side_effect=RuntimeError("db down")
        ),
        mock.patch.object(
            stats_cache, "find_lookup_stats", side_effect=RuntimeError("db down")
        ),
        mock.patch.object(
            featured_song, "pick_random_song", side_effect=RuntimeError("db down")
        ),
    ):
        rv = app.test_client().get("/")
        assert rv.status_code == 200
        assert "Lower Your Eyelids to Die With the Sun" in rv.text
        assert "The database today" not in rv.text

        assert app.test_client().get("/about").status_code == 200


def test_featured_song_is_computed_by_one_request_at_a_time(app: Flask) -> None:
    from acoustid.web import featured_song, stats_cache

    redis = FakeRedis()
    redis.store[featured_song.FEATURED_SONG_KEY + ":lock"] = b"1"
    with (
        app.test_request_context(),
        mock.patch.object(stats_cache.db, "get_redis", return_value=redis),
        mock.patch.object(featured_song, "pick_random_song") as pick,
    ):
        song = featured_song.get_featured_song([1, 2, 3])
    assert song["name"] == "Lower Your Eyelids to Die With the Sun"
    assert pick.call_count == 0


def test_pick_random_song(app: Flask) -> None:
    from acoustid import tables as schema
    from acoustid.data.fingerprint import insert_fingerprint
    from acoustid.web.featured_song import pick_random_song
    from tests import TEST_1A_FP_RAW
    from tests.test_data_musicbrainz import insert_artist_credit, insert_recording

    script = app.acoustid_script  # type: ignore
    with script.context() as ctx:
        mb_db = ctx.db.get_musicbrainz_db()
        artist_credit = insert_artist_credit(mb_db, "Picked Artist")
        recording = insert_recording(
            mb_db, "b81f83ee-4da4-11e0-9ed8-0025225356f3", "Picked Song", artist_credit
        )
        fp_db = ctx.db.get_fingerprint_db()
        fingerprint_id = insert_fingerprint(
            fp_db,
            ctx.db.get_ingest_db(),
            {"fingerprint": TEST_1A_FP_RAW * 3, "length": 300, "track_id": 1},
        )
        fp_db.execute(
            schema.fingerprint.update()
            .where(schema.fingerprint.c.id == fingerprint_id)
            .values(submission_count=5)
        )
        ctx.db.session.commit()
    try:
        with app.test_request_context():
            song = pick_random_song()
        assert song is not None
        assert song["name"] == "Picked Song"
        assert song["artist"] == "Picked Artist"
        assert song["track"] == "eb31d1c3-950e-468b-9e36-e46fa75b1291"
        assert len(song["fingerprint"]) == 948
    finally:
        with script.context() as ctx:
            ctx.db.get_fingerprint_db().execute(
                schema.fingerprint.delete().where(
                    schema.fingerprint.c.id == fingerprint_id
                )
            )
            mb_db = ctx.db.get_musicbrainz_db()
            mb_db.execute(
                schema.mb_recording.delete().where(
                    schema.mb_recording.c.id == recording
                )
            )
            mb_db.execute(
                schema.mb_artist_credit_name.delete().where(
                    schema.mb_artist_credit_name.c.artist_credit == artist_credit
                )
            )
            mb_db.execute(
                schema.mb_artist_credit.delete().where(
                    schema.mb_artist_credit.c.id == artist_credit
                )
            )
            mb_db.execute(
                schema.mb_artist.delete().where(
                    schema.mb_artist.c.name == "Picked Artist"
                )
            )
            ctx.db.session.commit()


def test_mbid_page_rejects_invalid_ids(app: Flask) -> None:
    rv = app.test_client().get("/mbid/not-a-uuid")
    assert rv.status_code == 404
    assert "is not a MusicBrainz recording ID" in rv.text


def test_track_page_metadata_links_keep_disabled_recordings(app: Flask) -> None:
    rv = app.test_client().get("/track/eb31d1c3-950e-468b-9e36-e46fa75b1291?disabled=1")
    assert "?metadata=raw&amp;disabled=1#metadata" in rv.text


def test_replacing_the_api_key_requires_post_and_a_token(app: Flask) -> None:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = 2

    assert client.get("/new-api-key").status_code == 405
    assert "user2key" in client.get("/api-key").text

    try:
        # Without the token from the account page, nothing changes.
        assert client.post("/new-api-key").status_code == 400
        assert (
            client.post("/new-api-key", data={"csrf_token": "wrong"}).status_code == 400
        )
        assert "user2key" in client.get("/api-key").text

        with client.session_transaction() as flask_session:
            token = flask_session["api_key_csrf_token"]
        rv = client.post("/new-api-key", data={"csrf_token": token})
        assert rv.status_code == 302
        assert "user2key" not in client.get("/api-key").text
    finally:
        from acoustid import tables as schema

        with app.acoustid_script.context() as ctx:  # type: ignore
            ctx.db.get_app_db().execute(
                schema.account.update()
                .where(schema.account.c.id == 2)
                .values(apikey="user2key")
            )
            ctx.db.session.commit()


def test_home_page_labels_old_search_counts_with_their_date(app: Flask) -> None:
    from acoustid.web import stats_cache

    lookups = [
        {
            "date": datetime.date(2020, 1, 2),
            "count": 1234,
            "count_hits": 1000,
            "count_nohits": 234,
        }
    ]
    with (
        mock.patch.object(
            stats_cache, "find_current_stats", return_value={"track.all": 10}
        ),
        mock.patch.object(stats_cache, "find_lookup_stats", return_value=lookups),
    ):
        rv = app.test_client().get("/")
    assert "Searches on 2020-01-02" in rv.text
    assert "Searches yesterday" not in rv.text


def test_mbid_page(app: Flask) -> None:
    from acoustid import tables as schema
    from tests.test_data_musicbrainz import insert_artist_credit, insert_recording

    script = app.acoustid_script  # type: ignore
    with script.context() as ctx:
        mb_db = ctx.db.get_musicbrainz_db()
        artist_credit = insert_artist_credit(mb_db, "Linked <Artist>")
        recording = insert_recording(
            mb_db, "b81f83ee-4da4-11e0-9ed8-0025225356f3", "Linked Song", artist_credit
        )
        ctx.db.get_fingerprint_db().execute(
            schema.track_mbid.insert().values(
                track_id=1,
                mbid="11111111-2222-3333-4444-555555555555",
                submission_count=1,
                disabled=False,
            )
        )
        ctx.db.session.commit()
    try:
        client = app.test_client()
        rv = client.get("/mbid/B81F83EE-4DA4-11E0-9ED8-0025225356F3")
        assert rv.status_code == 200
        assert "Linked Song" in rv.text
        # Names from MusicBrainz are escaped like any other data.
        assert "Linked &lt;Artist&gt;" in rv.text
        assert "eb31d1c3-950e-468b-9e36-e46fa75b1291" in rv.text
        # The track is also linked to a recording we have no metadata for,
        # which can only be linked to on MusicBrainz.
        assert (
            'href="https://musicbrainz.org/recording/'
            '11111111-2222-3333-4444-555555555555"' in rv.text
        )
        assert "/mbid/11111111-2222-3333-4444-555555555555" not in rv.text
        # Expanding the AcoustID lists every recording it is linked to,
        # this one included.
        assert 'aria-controls="links-1"' in rv.text
        assert "Recordings linked to A" in rv.text
        assert "this page" in rv.text
        assert "not in MusicBrainz" in rv.text
    finally:
        with script.context() as ctx:
            ctx.db.get_fingerprint_db().execute(
                schema.track_mbid.delete().where(
                    schema.track_mbid.c.mbid == "11111111-2222-3333-4444-555555555555"
                )
            )
            mb_db = ctx.db.get_musicbrainz_db()
            mb_db.execute(
                schema.mb_recording.delete().where(
                    schema.mb_recording.c.id == recording
                )
            )
            mb_db.execute(
                schema.mb_artist_credit_name.delete().where(
                    schema.mb_artist_credit_name.c.artist_credit == artist_credit
                )
            )
            mb_db.execute(
                schema.mb_artist_credit.delete().where(
                    schema.mb_artist_credit.c.id == artist_credit
                )
            )
            mb_db.execute(
                schema.mb_artist.delete().where(
                    schema.mb_artist.c.name == "Linked <Artist>"
                )
            )
            ctx.db.session.commit()


class FakeResponse:
    """Just enough of a requests response for the OAuth paths."""

    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def json(self) -> object:
        return json.loads(self.content)


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        return self.response


def stub_musicbrainz_oauth(
    monkeypatch: pytest.MonkeyPatch,
    token_body: bytes,
    userinfo_body: bytes = b'{"sub": "mb-user"}',
    token_status: int = 200,
    userinfo_status: int = 200,
) -> None:
    monkeypatch.setattr(
        OAuth2Service,
        "get_raw_access_token",
        lambda self, *a, **k: FakeResponse(token_body, token_status),
    )
    monkeypatch.setattr(
        OAuth2Service,
        "get_session",
        lambda self, token: FakeSession(FakeResponse(userinfo_body, userinfo_status)),
    )


def attempt_musicbrainz_login(app: Flask) -> Any:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["mb_login_token"] = "the-token-we-issued"
    state = URLSafeSerializer(app.config["SECRET_KEY"]).dumps(
        {"return_url": None, "token": "the-token-we-issued"}
    )
    return client.get(
        "/login/musicbrainz",
        query_string={"code": "an-authorization-code", "state": state},
    )


# The four Bugsink issues this retires are all the same mistake: a response
# that is not the happy path was treated as impossible. A stale or replayed
# authorization code is a user action, not an incident, so each of these must
# be a warning and a message on the login page rather than an error event.
MALFORMED_OAUTH_RESPONSES = [
    pytest.param(
        {
            "token_body": b'{"error":"invalid_grant","error_description":"Invalid authorization code"}'
        },
        id="token endpoint reports invalid_grant",
    ),
    pytest.param(
        {
            "token_body": b'{"error_description":"Invalid authorization code","error":"invalid_grant"}'
        },
        id="same, with the JSON keys the other way round",
    ),
    pytest.param(
        {"token_body": b"<html>502 Bad Gateway</html>", "token_status": 502},
        id="token endpoint returns a non-JSON body",
    ),
    pytest.param(
        {
            "token_body": b'{"access_token":"a-secret-token"}',
            "userinfo_body": b"<html>502 Bad Gateway</html>",
            "userinfo_status": 502,
        },
        id="userinfo returns a non-JSON body",
    ),
    pytest.param(
        {
            "token_body": b'{"access_token":"a-secret-token"}',
            "userinfo_body": b'{"name":"someone"}',
        },
        id="userinfo carries no sub",
    ),
]


@pytest.mark.parametrize("stub", MALFORMED_OAUTH_RESPONSES)
def test_musicbrainz_login_failures_are_warnings_not_errors(
    app: Flask, monkeypatch: pytest.MonkeyPatch, caplog, stub: dict
) -> None:
    stub_musicbrainz_oauth(monkeypatch, **stub)

    with caplog.at_level(logging.DEBUG):
        rv = attempt_musicbrainz_login(app)

    # the user is sent back to the login page with something to act on
    assert rv.status_code == 302
    assert urlparse(rv.headers["Location"]).path == "/login"
    assert parse_qs(urlparse(rv.headers["Location"]).query)["error"]

    # and nothing is reported as a server error, which is what used to turn
    # each of these into a Bugsink issue
    assert [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR] == []
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_musicbrainz_login_never_logs_the_access_token(
    app: Flask, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    """A token response that is missing something can still carry a token.

    The old code let rauth raise a KeyError whose message was the whole body,
    so this is the path by which a token could have reached the logs.
    """
    stub_musicbrainz_oauth(
        monkeypatch,
        token_body=b'{"access_token":"a-secret-token","error":"invalid_scope"}',
        userinfo_body=b'{"name":"someone"}',
    )

    with caplog.at_level(logging.DEBUG):
        attempt_musicbrainz_login(app)

    assert "a-secret-token" not in caplog.text


def test_musicbrainz_login_succeeds_when_the_responses_are_well_formed(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_musicbrainz_oauth(
        monkeypatch,
        token_body=b'{"access_token":"a-secret-token"}',
        userinfo_body=b'{"sub":"mb-user-42"}',
    )

    rv = attempt_musicbrainz_login(app)

    assert rv.status_code == 302
    assert urlparse(rv.headers["Location"]).path != "/login"


MODERATED_MBID = "b81f83ee-4da4-11e0-9ed8-0025225356f3"
TRACK_1_GID = "eb31d1c3-950e-468b-9e36-e46fa75b1291"
TRACK_2_GID = "92732e4b-97c6-4250-b237-1636384d466f"


@pytest.fixture()
def edit_history(app: Flask, moderator: int):
    """A recording in the mirror, two links to it, and a change to each.

    The second link is disabled, which is the case worth constructing: the
    recording page hides disabled links, so it is the one whose history would
    be invisible if the page only looked at what it displays.
    """
    from acoustid import tables as schema

    script = app.acoustid_script  # type: ignore
    with script.context() as ctx:
        mb_db = ctx.db.get_musicbrainz_db()
        mb_db.execute(
            sql.text(
                "INSERT INTO musicbrainz.artist_credit "
                "(id, name, artist_count, edits_pending) "
                "VALUES (9100, 'Test Artist', 1, 0)"
            )
        )
        mb_db.execute(
            sql.text(
                "INSERT INTO musicbrainz.recording "
                "(id, gid, name, artist_credit, length, comment, "
                " edits_pending, video) "
                "VALUES (9100, :gid, 'Test Recording', 9100, 200000, '', 0, false)"
            ).bindparams(gid=MODERATED_MBID)
        )

        fp_db = ctx.db.get_fingerprint_db()
        hidden_link_id = fp_db.execute(
            schema.track_mbid.insert()
            .values(track_id=2, mbid=MODERATED_MBID, submission_count=1, disabled=True)
            .returning(schema.track_mbid.c.id)
        ).scalar_one()
        visible_link_id = fp_db.execute(
            sql.select(schema.track_mbid.c.id).where(
                sql.and_(
                    schema.track_mbid.c.track_id == 1,
                    schema.track_mbid.c.mbid == MODERATED_MBID,
                )
            )
        ).scalar_one()

        ingest_db = ctx.db.get_ingest_db()
        ingest_db.execute(
            schema.track_mbid_change.insert().values(
                track_mbid_id=visible_link_id,
                account_id=moderator,
                disabled=False,
                note="relinked after review",
            )
        )
        ingest_db.execute(
            schema.track_mbid_change.insert().values(
                track_mbid_id=hidden_link_id,
                account_id=moderator,
                disabled=True,
                note="wrong recording",
            )
        )
        ctx.db.session.commit()

    yield moderator

    with script.context() as ctx:
        ctx.db.get_ingest_db().execute(schema.track_mbid_change.delete())
        ctx.db.get_fingerprint_db().execute(
            schema.track_mbid.delete().where(schema.track_mbid.c.track_id == 2)
        )
        mb_db = ctx.db.get_musicbrainz_db()
        mb_db.execute(sql.text("DELETE FROM musicbrainz.recording WHERE id = 9100"))
        mb_db.execute(sql.text("DELETE FROM musicbrainz.artist_credit WHERE id = 9100"))
        ctx.db.session.commit()


def test_mbid_page_hides_editing_history_from_anonymous_visitors(
    app: Flask, edit_history: int
) -> None:
    rv = app.test_client().get("/mbid/%s" % MODERATED_MBID)
    assert rv.status_code == 200
    assert "Editing history" not in rv.text
    assert "wrong recording" not in rv.text


def test_mbid_page_shows_editing_history_to_moderators(
    app: Flask, edit_history: int
) -> None:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = edit_history

    rv = client.get("/mbid/%s" % MODERATED_MBID)
    assert rv.status_code == 200
    assert "Editing history" in rv.text
    assert TRACK_1_GID in rv.text


def test_mbid_page_history_covers_links_the_page_does_not_show(
    app: Flask, edit_history: int
) -> None:
    """The point of reading history from all links rather than visible ones.

    An unlink sets disabled, and the recording page hides disabled links, so
    the edits most worth seeing belong to tracks absent from the list. Here
    track 2's link is disabled: its AcoustID is not in the table, and its
    change still has to appear in the history.
    """
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = edit_history

    rv = client.get("/mbid/%s" % MODERATED_MBID)
    assert rv.status_code == 200
    # Shown once in the history, and not in the list of linked AcoustIDs.
    assert "Show 1 disabled link" in rv.text
    assert TRACK_2_GID in rv.text


def test_audit_page_requires_a_moderator(app: Flask) -> None:
    client = app.test_client()
    assert client.get("/edits").status_code == 302

    with client.session_transaction() as flask_session:
        flask_session["id"] = 2  # no MusicBrainz account linked
    assert client.get("/edits").status_code == 404


def test_audit_page_lists_edits_with_their_notes(app: Flask, edit_history: int) -> None:
    """The note is shown here and nowhere else -- it is the reason for an edit."""
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = edit_history

    rv = client.get("/edits")
    assert rv.status_code == 200
    assert "relinked after review" in rv.text
    assert "wrong recording" in rv.text
    assert MODERATED_MBID in rv.text
    assert TRACK_1_GID in rv.text


def test_audit_page_filters_by_recording(app: Flask, edit_history: int) -> None:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = edit_history

    rv = client.get("/edits?mbid=%s" % MODERATED_MBID)
    assert rv.status_code == 200
    assert "wrong recording" in rv.text

    # A recording with no links has no edits, rather than all of them.
    rv = client.get("/edits?mbid=54b7b412-fc69-4fc7-8c96-17800eda3a98")
    assert rv.status_code == 200
    assert "wrong recording" not in rv.text
    assert "No edits match this filter" in rv.text


def test_audit_page_filters_by_acoustid(app: Flask, edit_history: int) -> None:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = edit_history

    rv = client.get("/edits?acoustid=%s" % TRACK_2_GID)
    assert rv.status_code == 200
    assert "wrong recording" in rv.text
    assert "relinked after review" not in rv.text


def test_audit_page_rejects_identifiers_that_are_not_uuids(
    app: Flask, edit_history: int
) -> None:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = edit_history

    assert client.get("/edits?mbid=nope").status_code == 404
    assert client.get("/edits?acoustid=nope").status_code == 404
    # A well-formed AcoustID that does not exist is also a 404, rather than an
    # unfiltered listing of every edit on the site.
    rv = client.get("/edits?acoustid=00000000-0000-0000-0000-000000000000")
    assert rv.status_code == 404


def test_inline_history_is_capped_and_offers_the_rest(
    app: Flask, edit_history: int
) -> None:
    """The inline list is a summary, with the audit page for the whole thing.

    Uncapped, a heavily moderated recording pushes everything below the
    history off the page, which is what this replaced.
    """
    from acoustid import tables as schema
    from acoustid.web.views.metadata import MAX_INLINE_EDITS

    script = app.acoustid_script  # type: ignore
    with script.context() as ctx:
        link_id = (
            ctx.db.get_fingerprint_db()
            .execute(
                sql.select(schema.track_mbid.c.id).where(
                    sql.and_(
                        schema.track_mbid.c.track_id == 1,
                        schema.track_mbid.c.mbid == MODERATED_MBID,
                    )
                )
            )
            .scalar_one()
        )
        for i in range(MAX_INLINE_EDITS):
            ctx.db.get_ingest_db().execute(
                schema.track_mbid_change.insert().values(
                    track_mbid_id=link_id,
                    account_id=edit_history,
                    disabled=bool(i % 2),
                    note="filler %d" % i,
                )
            )
        ctx.db.session.commit()

    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = edit_history

    rv = client.get("/mbid/%s" % MODERATED_MBID)
    assert rv.status_code == 200
    # The fixture's two changes plus MAX_INLINE_EDITS fillers is more than fits.
    assert "Show all edits" in rv.text
    assert rv.text.count("musicbrainz.org/user/moderator") == MAX_INLINE_EDITS
    # And the audit page it points at has them all.
    rv = client.get("/edits?mbid=%s" % MODERATED_MBID)
    assert rv.status_code == 200
    assert rv.text.count("musicbrainz.org/user/moderator") == MAX_INLINE_EDITS + 2
