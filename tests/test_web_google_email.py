# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import base64
import json
import uuid
from types import SimpleNamespace
from typing import Any, Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from flask import Flask
from rauth import OAuth2Service
from sqlalchemy import sql

from acoustid import tables as schema
from acoustid.data.email import set_account_email
from tests import make_web_application


@pytest.fixture()
def app(config_file: str) -> Iterator[Flask]:
    app = make_web_application(config_file)
    app.config["TESTING"] = True
    yield app
    with app.acoustid_script.context() as ctx:  # type: ignore
        conn = ctx.db.get_app_db()
        conn.execute(schema.account_google.delete())
        conn.execute(schema.account_openid.delete())
        conn.execute(schema.account.delete().where(schema.account.c.id > 2))
        conn.execute(schema.account.update().values(email=None, email_verified=None))
        ctx.db.session.commit()


def unique_address(domain: str = "gmail.com") -> str:
    return "test-%s@%s" % (uuid.uuid4().hex, domain)


def b64(data: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


def google_login(
    app: Flask, monkeypatch: pytest.MonkeyPatch, claims: dict[str, Any]
) -> int:
    """Signs in through the Google callback, with the token endpoint faked to
    return an ID token with these claims. Returns the signed-in account."""
    id_token = "%s.%s.sig" % (b64({"alg": "RS256"}), b64(claims))
    content = json.dumps({"id_token": id_token}).encode()
    monkeypatch.setattr(
        OAuth2Service,
        "get_raw_access_token",
        lambda self, *args, **kwargs: SimpleNamespace(content=content),
    )
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["google_login_token"] = "state"
    rv = client.get("/login/google", query_string={"code": "c", "state": "state"})
    assert rv.status_code == 302
    with client.session_transaction() as flask_session:
        return flask_session["id"]


def account_email(app: Flask, account_id: int) -> tuple[str | None, Any]:
    with app.acoustid_script.context() as ctx:  # type: ignore
        account = schema.account
        row = (
            ctx.db.get_app_db()
            .execute(
                sql.select(account.c.email, account.c.email_verified).where(
                    account.c.id == account_id
                )
            )
            .one()
        )
        return row.email, row.email_verified


def test_requests_the_email_scope(app: Flask) -> None:
    rv = app.test_client().get("/login/google")
    query = parse_qs(urlparse(rv.headers["Location"]).query)
    assert query["scope"] == ["openid email"]


@pytest.mark.parametrize("verified", [True, "true"])
def test_stores_a_verified_address(
    app: Flask, monkeypatch: pytest.MonkeyPatch, verified: Any
) -> None:
    email = unique_address()
    claims = {
        "sub": uuid.uuid4().hex,
        "email": email.upper(),
        "email_verified": verified,
    }
    account_id = google_login(app, monkeypatch, claims)
    stored, at = account_email(app, account_id)
    assert stored == email
    assert at is not None


@pytest.mark.parametrize(
    "claims",
    [
        {"email_verified": False},
        {"email_verified": "false"},
        {},
        {"email_verified": True, "email": ""},
        {"email_verified": True, "email": "not an address"},
        {"email_verified": 1},
        {"email_verified": "True"},
        # Not hosted by Google: verified once, maybe long ago.
        {"email_verified": True, "email": unique_address("example.com")},
    ],
)
def test_ignores_an_unverified_or_missing_address(
    app: Flask, monkeypatch: pytest.MonkeyPatch, claims: dict[str, Any]
) -> None:
    claims = {"sub": uuid.uuid4().hex, "email": unique_address(), **claims}
    account_id = google_login(app, monkeypatch, claims)
    assert account_email(app, account_id) == (None, None)


def test_keeps_an_address_the_account_has(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    sub = uuid.uuid4().hex
    first = unique_address()
    account_id = google_login(
        app, monkeypatch, {"sub": sub, "email": first, "email_verified": True}
    )
    second = unique_address()
    assert (
        google_login(
            app, monkeypatch, {"sub": sub, "email": second, "email_verified": True}
        )
        == account_id
    )
    assert account_email(app, account_id)[0] == first


def test_leaves_an_address_another_account_has(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = unique_address()
    with app.acoustid_script.context() as ctx:  # type: ignore
        assert set_account_email(ctx.db.get_app_db(), 2, email)
        ctx.db.session.commit()
    claims = {"sub": uuid.uuid4().hex, "email": email, "email_verified": True}
    account_id = google_login(app, monkeypatch, claims)
    # Signed in all the same, to its own account, without the address.
    assert account_id != 2
    assert account_email(app, account_id) == (None, None)
    assert account_email(app, 2)[0] == email


@pytest.mark.parametrize(
    "domain,hd",
    [("googlemail.com", None), ("example.com", "example.com")],
)
def test_stores_addresses_google_hosts(
    app: Flask, monkeypatch: pytest.MonkeyPatch, domain: str, hd: str | None
) -> None:
    email = unique_address(domain)
    claims: dict[str, Any] = {
        "sub": uuid.uuid4().hex,
        "email": email,
        "email_verified": True,
    }
    if hd is not None:
        claims["hd"] = hd
    account_id = google_login(app, monkeypatch, claims)
    assert account_email(app, account_id)[0] == email


def test_conflict_keeps_the_google_link(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = unique_address()
    with app.acoustid_script.context() as ctx:  # type: ignore
        assert set_account_email(ctx.db.get_app_db(), 2, email)
        ctx.db.session.commit()
    claims = {"sub": uuid.uuid4().hex, "email": email, "email_verified": True}
    first = google_login(app, monkeypatch, claims)
    assert google_login(app, monkeypatch, claims) == first


def test_migrated_openid_account_gets_the_address(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    openid = "https://www.google.com/accounts/o8/id?id=%s" % uuid.uuid4().hex
    with app.acoustid_script.context() as ctx:  # type: ignore
        conn = ctx.db.get_app_db()
        account_id = conn.execute(
            schema.account.insert()
            .values(name="OpenID User", apikey=uuid.uuid4().hex[:10])
            .returning(schema.account.c.id)
        ).scalar_one()
        conn.execute(
            schema.account_openid.insert().values(account_id=account_id, openid=openid)
        )
        ctx.db.session.commit()
    email = unique_address()
    claims = {
        "sub": uuid.uuid4().hex,
        "openid_id": openid,
        "email": email,
        "email_verified": True,
    }
    assert google_login(app, monkeypatch, claims) == account_id
    assert account_email(app, account_id)[0] == email


def test_does_not_replace_an_address_confirmed_meanwhile(
    app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The account page confirms an address after the Google callback has
    # loaded the account, and before it writes.
    confirmed = unique_address()
    real_set = set_account_email

    def confirm_first(conn: Any, account_id: int, email: str, **kwargs: Any) -> bool:
        assert real_set(conn, account_id, confirmed)
        return real_set(conn, account_id, email, **kwargs)

    monkeypatch.setattr("acoustid.web.views.user.set_account_email", confirm_first)
    claims = {
        "sub": uuid.uuid4().hex,
        "email": unique_address(),
        "email_verified": True,
    }
    account_id = google_login(app, monkeypatch, claims)
    assert account_email(app, account_id)[0] == confirmed
