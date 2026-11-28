# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Linking a MusicBrainz account to an account signed in some other way."""

import json
import uuid
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from flask import Flask
from flask.testing import FlaskClient
from itsdangerous import URLSafeSerializer
from rauth import OAuth2Service
from sqlalchemy import sql

from acoustid import tables as schema
from tests import make_web_application

ACCOUNT_ID = 2
OTHER_ACCOUNT_ID = 1


@pytest.fixture()
def app(config_file: str) -> Iterator[Flask]:
    app = make_web_application(config_file)
    app.config["TESTING"] = True
    yield app
    with app.acoustid_script.context() as ctx:  # type: ignore
        ctx.db.get_app_db().execute(
            schema.account.update()
            .where(schema.account.c.id.in_([ACCOUNT_ID, OTHER_ACCOUNT_ID]))
            .values(mbuser=None, email=None, email_verified=None)
        )
        ctx.db.session.commit()


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = ACCOUNT_ID
    return client


def mb_name() -> str:
    return "mb-%s" % uuid.uuid4().hex[:12]


def set_account(app: Flask, account_id: int, **values: Any) -> None:
    with app.acoustid_script.context() as ctx:  # type: ignore
        ctx.db.get_app_db().execute(
            schema.account.update()
            .where(schema.account.c.id == account_id)
            .values(**values)
        )
        ctx.db.session.commit()


def get_mbuser(app: Flask, account_id: int) -> str | None:
    with app.acoustid_script.context() as ctx:  # type: ignore
        return (
            ctx.db.get_app_db()
            .execute(
                sql.select(schema.account.c.mbuser).where(
                    schema.account.c.id == account_id
                )
            )
            .scalar()
        )


def csrf_token(client: FlaskClient) -> str:
    client.get("/api-key")
    with client.session_transaction() as flask_session:
        return flask_session["api_key_csrf_token"]


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content
        self.status_code = 200

    def json(self) -> object:
        return json.loads(self.content)


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        return self.response


def stub_musicbrainz(monkeypatch: pytest.MonkeyPatch, sub: str) -> None:
    monkeypatch.setattr(
        OAuth2Service,
        "get_raw_access_token",
        lambda self, *a, **k: FakeResponse(b'{"access_token": "a-token"}'),
    )
    body = json.dumps({"sub": sub}).encode()
    monkeypatch.setattr(
        OAuth2Service,
        "get_session",
        lambda self, token: FakeSession(FakeResponse(body)),
    )


def start_link(client: FlaskClient, return_url: str | None = None) -> dict[str, Any]:
    """Press the link button; the state MusicBrainz would hand back."""
    form = {"csrf_token": csrf_token(client)}
    if return_url is not None:
        form["return_url"] = return_url
    rv = client.post("/account/musicbrainz/link", data=form)
    assert rv.status_code == 302
    location = urlparse(rv.headers["Location"])
    assert location.netloc == "musicbrainz.org"
    return parse_qs(location.query)


def come_back(client: FlaskClient, query: dict[str, Any]) -> Any:
    return client.get(
        "/login/musicbrainz",
        query_string={"code": "an-authorization-code", "state": query["state"][0]},
    )


def test_link_needs_the_csrf_token(app: Flask, client: FlaskClient) -> None:
    rv = client.post("/account/musicbrainz/link", data={"csrf_token": "wrong"})
    assert rv.status_code == 400
    rv = client.post("/account/musicbrainz/link")
    assert rv.status_code == 400


def test_link_needs_a_signed_in_user(app: Flask) -> None:
    rv = app.test_client().post("/account/musicbrainz/link")
    assert rv.status_code == 302
    assert urlparse(rv.headers["Location"]).path == "/login"


def test_link_state_names_the_account(app: Flask, client: FlaskClient) -> None:
    query = start_link(client)
    state = URLSafeSerializer(app.config["SECRET_KEY"]).loads(query["state"][0])
    assert state["link"] == ACCOUNT_ID
    with client.session_transaction() as flask_session:
        assert state["token"] == flask_session["mb_login_token"]


def test_link(app: Flask, client: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    name = mb_name()
    stub_musicbrainz(monkeypatch, name)

    rv = come_back(client, start_link(client))

    assert rv.status_code == 302
    location = urlparse(rv.headers["Location"])
    assert (location.path, location.fragment) == ("/api-key", "")
    assert get_mbuser(app, ACCOUNT_ID) == name
    with client.session_transaction() as flask_session:
        # Still the same account, not one made for the MusicBrainz user.
        assert flask_session["id"] == ACCOUNT_ID

    rv = client.get("/api-key")
    assert "is now linked to the MusicBrainz account %s" % name in rv.text
    assert "Unlink MusicBrainz account" in rv.text


def test_link_returns_to_the_edit(
    app: Flask, client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_musicbrainz(monkeypatch, mb_name())
    edit_url = "http://localhost/edit/toggle-track-mbid?track_gid=x&mbid=y&state=1"

    rv = come_back(client, start_link(client, return_url=edit_url))

    assert rv.status_code == 302
    assert rv.headers["Location"] == edit_url


def test_link_does_not_return_elsewhere(
    app: Flask, client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_musicbrainz(monkeypatch, mb_name())

    rv = come_back(client, start_link(client, return_url="https://evil.example/"))

    assert urlparse(rv.headers["Location"]).path == "/api-key"


def test_link_conflict(
    app: Flask, client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    name = mb_name()
    set_account(app, OTHER_ACCOUNT_ID, mbuser=name)
    stub_musicbrainz(monkeypatch, name)

    rv = come_back(client, start_link(client))

    assert urlparse(rv.headers["Location"]).path == "/api-key"
    assert get_mbuser(app, ACCOUNT_ID) is None
    assert get_mbuser(app, OTHER_ACCOUNT_ID) == name
    with client.session_transaction() as flask_session:
        assert flask_session["id"] == ACCOUNT_ID

    rv = client.get("/api-key")
    assert "<b>%s</b> is already linked to a different" % name in rv.text
    assert "info@acoustid.org" in rv.text
    # Shown once.
    rv = client.get("/api-key")
    assert "info@acoustid.org" not in rv.text


def test_link_signed_out_in_the_meantime(
    app: Flask, client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_musicbrainz(monkeypatch, mb_name())
    query = start_link(client)
    with client.session_transaction() as flask_session:
        flask_session["id"] = OTHER_ACCOUNT_ID

    rv = come_back(client, query)

    assert urlparse(rv.headers["Location"]).path == "/api-key"
    assert get_mbuser(app, ACCOUNT_ID) is None
    assert get_mbuser(app, OTHER_ACCOUNT_ID) is None


def test_link_rejects_bad_state(
    app: Flask, client: FlaskClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_musicbrainz(monkeypatch, mb_name())
    start_link(client)
    forged = URLSafeSerializer(app.config["SECRET_KEY"]).dumps(
        {"return_url": None, "token": "not-ours", "link": ACCOUNT_ID}
    )

    rv = come_back(client, {"state": [forged]})

    assert urlparse(rv.headers["Location"]).path == "/api-key"
    assert get_mbuser(app, ACCOUNT_ID) is None


def test_account_page_offers_link(app: Flask, client: FlaskClient) -> None:
    rv = client.get("/api-key")
    assert 'action="/account/musicbrainz/link"' in rv.text
    assert "Unlink" not in rv.text


def test_unlink(app: Flask, client: FlaskClient) -> None:
    set_account(app, ACCOUNT_ID, mbuser=mb_name(), email="someone@example.com")

    rv = client.post(
        "/account/musicbrainz/unlink", data={"csrf_token": csrf_token(client)}
    )

    assert rv.status_code == 302
    assert get_mbuser(app, ACCOUNT_ID) is None
    rv = client.get("/api-key")
    assert "no longer linked to a MusicBrainz account" in rv.text


def test_unlink_needs_an_email_address(app: Flask, client: FlaskClient) -> None:
    name = mb_name()
    set_account(app, ACCOUNT_ID, mbuser=name)

    rv = client.get("/api-key")
    assert "Add an email address first" in rv.text
    assert 'action="/account/musicbrainz/unlink"' not in rv.text

    client.post("/account/musicbrainz/unlink", data={"csrf_token": csrf_token(client)})
    assert get_mbuser(app, ACCOUNT_ID) == name


def test_unlink_needs_the_csrf_token(app: Flask, client: FlaskClient) -> None:
    name = mb_name()
    set_account(app, ACCOUNT_ID, mbuser=name, email="someone@example.com")

    rv = client.post("/account/musicbrainz/unlink", data={"csrf_token": "wrong"})

    assert rv.status_code == 400
    assert get_mbuser(app, ACCOUNT_ID) == name


def test_edit_without_musicbrainz_offers_link(app: Flask, client: FlaskClient) -> None:
    rv = client.get(
        "/edit/toggle-track-mbid",
        query_string={
            "track_id": 1,
            "mbid": "b81f83ee-4da4-11e0-9ed8-0025225356f3",
            "state": 1,
        },
    )
    assert rv.status_code == 200
    assert "MusicBrainz account required" in rv.text
    assert 'action="/account/musicbrainz/link"' in rv.text
    return_url = parse_qs(
        urlparse(
            rv.text.split('name="return_url" value="')[1]
            .split('"')[0]
            .replace("&amp;", "&")
        ).query
    )
    assert return_url["mbid"] == ["b81f83ee-4da4-11e0-9ed8-0025225356f3"]
    assert return_url["state"] == ["1"]
    assert "track_gid" in return_url


def test_track_page_buttons_only_for_signed_in(app: Flask, client: FlaskClient) -> None:
    rv = app.test_client().get("/track/eb31d1c3-950e-468b-9e36-e46fa75b1291")
    assert rv.status_code == 200
    assert "toggle-track-mbid" not in rv.text

    rv = client.get("/track/eb31d1c3-950e-468b-9e36-e46fa75b1291")
    assert rv.status_code == 200
    assert "toggle-track-mbid" in rv.text
