# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from typing import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import sql

from acoustid import tables as schema
from acoustid.data.account import (
    USER_KEY_APPROVED,
    USER_KEY_CACHE_PREFIX,
    USER_KEY_DECLINED,
    USER_KEY_REVOKED,
    LinkRequest,
    UserKey,
    approve_user_key_link_request,
    create_user_key_link_request,
    format_link_code,
    lookup_user_api_key,
    read_cached_user_key,
)
from acoustid.web.views.link import MAX_FAILED_CODES_PER_HOUR
from tests import make_web_application

ACCOUNT_ID = 2


@pytest.fixture()
def app(config_file: str) -> Iterator[Flask]:
    app = make_web_application(config_file)
    app.config["TESTING"] = True
    yield app
    script = app.acoustid_script  # type: ignore
    with script.context() as ctx:
        ctx.db.get_app_db().execute(schema.account_application_key.delete())
        ctx.db.session.commit()
        for pattern in (USER_KEY_CACHE_PREFIX + "*", "linkcode:*"):
            for key in ctx.redis.scan_iter(pattern):
                ctx.redis.delete(key)


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = ACCOUNT_ID
    return client


def new_request(
    app: Flask, return_url: str | None = None, device: str = "nas"
) -> LinkRequest:
    with app.acoustid_script.context() as ctx:  # type: ignore
        req = create_user_key_link_request(ctx.db.get_app_db(), 1, device, return_url)
        ctx.db.session.commit()
    return req


def key_state(app: Flask, apikey: str) -> UserKey | None:
    with app.acoustid_script.context() as ctx:  # type: ignore
        return lookup_user_api_key(ctx.db.get_app_db(), apikey)


def cached_key(app: Flask, apikey: str) -> tuple[bool, UserKey | None]:
    return read_cached_user_key(app.acoustid_script.get_redis(), apikey)  # type: ignore


def csrf_token(client: FlaskClient) -> str:
    with client.session_transaction() as flask_session:
        return flask_session["link_csrf_token"]


def test_link_requires_sign_in(app: Flask) -> None:
    rv = app.test_client().get("/link?code=ABCD-EFGH")
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_consent_page(app: Flask, client: FlaskClient) -> None:
    req = new_request(app, return_url="http://192.168.1.10:8095/settings")
    rv = client.get("/link?code=" + format_link_code(req.link_code))
    assert rv.status_code == 200
    assert "Connect App 1?" in rv.text
    assert "nas" in rv.text
    assert "192.168.1.10:8095" in rv.text
    assert rv.headers["Content-Security-Policy"] == "frame-ancestors 'none'"
    assert rv.headers["X-Frame-Options"] == "DENY"


def test_consent_page_escapes_what_the_developer_and_client_chose(
    app: Flask, client: FlaskClient
) -> None:
    with app.acoustid_script.context() as ctx:  # type: ignore
        ctx.db.get_app_db().execute(
            schema.application.update()
            .where(schema.application.c.id == 1)
            .values(name="<b>App</b>")
        )
        ctx.db.session.commit()
    try:
        req = new_request(app, device="<img src=x>")
        rv = client.get("/link?code=" + req.link_code)
        assert "<b>App</b>" not in rv.text
        assert "&lt;b&gt;App&lt;/b&gt;" in rv.text
        assert "<img src=x>" not in rv.text
    finally:
        with app.acoustid_script.context() as ctx:  # type: ignore
            ctx.db.get_app_db().execute(
                schema.application.update()
                .where(schema.application.c.id == 1)
                .values(name="App 1")
            )
            ctx.db.session.commit()


def test_typed_code_is_normalized_and_skips_the_return_url(
    app: Flask, client: FlaskClient
) -> None:
    req = new_request(app, return_url="http://192.168.1.10:8095/")
    typed = " " + req.link_code.lower() + " "
    rv = client.get("/link", query_string={"code": typed, "entered": "1"})
    assert rv.status_code == 200
    assert "192.168.1.10" not in rv.text

    rv = client.post(
        "/link/approve",
        data={"code": typed, "entered": "1", "csrf_token": csrf_token(client)},
    )
    assert rv.status_code == 200
    assert "can now use AcoustID" in rv.text


def test_approve_redirects_back_and_publishes_the_key(
    app: Flask, client: FlaskClient
) -> None:
    req = new_request(app, return_url="http://192.168.1.10:8095/settings")
    code = format_link_code(req.link_code)
    client.get("/link?code=" + code)

    # Without the token from the consent page, nothing happens.
    assert client.post("/link/approve", data={"code": code}).status_code == 400
    assert key_state(app, req.apikey) == UserKey(None, 1, "pending")

    rv = client.post(
        "/link/approve", data={"code": code, "csrf_token": csrf_token(client)}
    )
    assert rv.status_code == 303
    assert rv.headers["Location"] == "http://192.168.1.10:8095/settings"
    approved = UserKey(ACCOUNT_ID, 1, USER_KEY_APPROVED)
    assert key_state(app, req.apikey) == approved
    assert cached_key(app, req.apikey) == (True, approved)

    # The code is used up.
    rv = client.post(
        "/link/approve", data={"code": code, "csrf_token": csrf_token(client)}
    )
    assert "That code is not valid" in rv.text


def test_decline(app: Flask, client: FlaskClient) -> None:
    req = new_request(app)
    client.get("/link?code=" + req.link_code)
    rv = client.post(
        "/link/decline",
        data={"code": req.link_code, "csrf_token": csrf_token(client)},
    )
    assert rv.status_code == 200
    assert "was not connected" in rv.text
    declined = UserKey(None, 1, USER_KEY_DECLINED)
    assert key_state(app, req.apikey) == declined
    assert cached_key(app, req.apikey) == (True, declined)


def test_wrong_codes_are_limited_per_account(app: Flask, client: FlaskClient) -> None:
    for _ in range(MAX_FAILED_CODES_PER_HOUR):
        rv = client.get("/link?code=ZZZZ-ZZZZ")
        assert "That code is not valid" in rv.text
    req = new_request(app)
    rv = client.get("/link?code=" + req.link_code)
    assert "Too many wrong codes" in rv.text
    assert "Approve" not in rv.text


def test_my_keys_and_revoke(app: Flask, client: FlaskClient) -> None:
    reqs = [new_request(app, device=device) for device in ("nas", "laptop", "pi")]
    with app.acoustid_script.context() as ctx:  # type: ignore
        for req in reqs:
            approve_user_key_link_request(
                ctx.db.get_app_db(), req.link_code, ACCOUNT_ID
            )
        ctx.db.session.commit()
    ids = {req.apikey: id_of(app, req.apikey) for req in reqs}

    rv = client.get("/my-keys")
    assert rv.status_code == 200
    assert "laptop" in rv.text and "pi" in rv.text
    assert rv.headers["X-Frame-Options"] == "DENY"
    token = csrf_token(client)

    assert (
        client.post("/my-keys/revoke", data={"id": ids[reqs[0].apikey]}).status_code
        == 400
    )
    rv = client.post(
        "/my-keys/revoke", data={"id": ids[reqs[0].apikey], "csrf_token": token}
    )
    assert rv.status_code == 303
    revoked = UserKey(ACCOUNT_ID, 1, USER_KEY_REVOKED)
    assert key_state(app, reqs[0].apikey) == revoked
    assert cached_key(app, reqs[0].apikey) == (True, revoked)
    assert key_state(app, reqs[1].apikey) == UserKey(ACCOUNT_ID, 1, USER_KEY_APPROVED)

    rv = client.post("/my-keys/revoke-all", data={"csrf_token": token})
    assert rv.status_code == 303
    for req in reqs:
        assert key_state(app, req.apikey) == revoked
        assert cached_key(app, req.apikey) == (True, revoked)


def test_cannot_revoke_another_accounts_key(app: Flask, client: FlaskClient) -> None:
    req = new_request(app)
    with app.acoustid_script.context() as ctx:  # type: ignore
        approve_user_key_link_request(ctx.db.get_app_db(), req.link_code, 1)
        ctx.db.session.commit()
    client.get("/my-keys")
    client.post(
        "/my-keys/revoke",
        data={"id": id_of(app, req.apikey), "csrf_token": csrf_token(client)},
    )
    assert key_state(app, req.apikey) == UserKey(1, 1, USER_KEY_APPROVED)


def id_of(app: Flask, apikey: str) -> int:
    table = schema.account_application_key
    with app.acoustid_script.context() as ctx:  # type: ignore
        return (
            ctx.db.get_app_db()
            .execute(sql.select(table.c.id).where(table.c.apikey == apikey))
            .scalar_one()
        )
