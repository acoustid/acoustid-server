from urllib.parse import parse_qs, urlparse

import pytest
from flask import Flask
from itsdangerous import URLSafeSerializer
from rauth import OAuth2Service

from acoustid.web import db
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
    assert "Welcome to AcoustID" in rv.text


def test_docs_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/docs")
    assert rv.status_code == 200
    assert "Documentation" in rv.text


def test_chromaprint_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/chromaprint")
    assert rv.status_code == 200


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
    assert "Basic statistics" in rv.text
    assert "Daily additions" in rv.text


def test_login_page(app: Flask) -> None:
    client = app.test_client()

    rv = client.get("/login")
    assert rv.status_code == 200


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
    assert rv.data.count(b"Custom Track") == 2
    assert rv.data.count(b"Custom Artist") == 2
    assert not db.session.registry.has()


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
