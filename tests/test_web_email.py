# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import re
import uuid
from typing import Any, Iterator
from unittest import mock
from urllib.parse import urlparse

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import sql

from acoustid import tables as schema
from acoustid.data.email import (
    CONFIRMATION_PREFIX,
    MAX_EMAILS_PER_ACCOUNT_PER_HOUR,
    MAX_EMAILS_PER_ADDRESS_PER_HOUR,
    RATE_LIMIT_PREFIX,
    find_account_by_email,
    mask_email,
    normalize_email,
    set_account_email,
)
from tests import make_web_application
from tests.test_mail import find_messages, get_message

ACCOUNT_ID = 2
OTHER_ACCOUNT_ID = 1


@pytest.fixture()
def app(config_file: str) -> Iterator[Flask]:
    app = make_web_application(config_file)
    app.config["TESTING"] = True
    yield app
    script = app.acoustid_script  # type: ignore
    with script.context() as ctx:
        ctx.db.get_app_db().execute(
            schema.account.update().values(email=None, email_verified=None)
        )
        ctx.db.session.commit()
        for pattern in (CONFIRMATION_PREFIX + "*", RATE_LIMIT_PREFIX + "*"):
            for key in ctx.redis.scan_iter(pattern):
                ctx.redis.delete(key)


def sign_in(client: FlaskClient, account_id: int) -> None:
    with client.session_transaction() as flask_session:
        flask_session["id"] = account_id


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    client = app.test_client()
    sign_in(client, ACCOUNT_ID)
    return client


def unique_address() -> str:
    return "test-%s@example.com" % uuid.uuid4().hex


def csrf_token(client: FlaskClient) -> str:
    client.get("/api-key")
    with client.session_transaction() as flask_session:
        return flask_session["api_key_csrf_token"]


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


def request_link(client: FlaskClient, email: str) -> Any:
    return client.post(
        "/account/email", data={"csrf_token": csrf_token(client), "email": email}
    )


def link_from_mail(email: str) -> str:
    [summary] = find_messages(email)
    message = get_message(summary["ID"])
    assert message["Subject"] == "Confirm your email address for AcoustID"
    match = re.search(r"https?://\S+/account/email/confirm\?token=\S+", message["Text"])
    assert match is not None
    assert match.group(0) in message["HTML"]
    url = urlparse(match.group(0))
    return url.path + "?" + url.query


def token_of(link: str) -> str:
    return link.split("token=", 1)[1]


def confirm(client: FlaskClient, link: str) -> Any:
    return client.post(
        "/account/email/confirm",
        data={"csrf_token": csrf_token(client), "token": token_of(link)},
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        ("user@example.com", "user@example.com"),
        ("  User@Example.COM ", "user@example.com"),
        ("first.last+tag@sub.example.co.uk", "first.last+tag@sub.example.co.uk"),
        ("user@example", None),
        ("user@example.", None),
        ("user@.example.com", None),
        ("user@example..com", None),
        ("user", None),
        ("", None),
        ("a@b.com, c@d.com", None),
        ("Name <user@example.com>", None),
        ("x" * 65 + "@example.com", None),
        ("user@" + "x" * 250 + ".com", None),
    ],
)
def test_normalize_email(value: str, expected: str | None) -> None:
    assert normalize_email(value) == expected


def test_mask_email() -> None:
    assert mask_email("lukas@example.com") == "l•••s@example.com"
    assert mask_email("ab@example.com") == "a•••@example.com"
    assert mask_email("a@example.com") == "a•••@example.com"


def test_account_page_without_email(client: FlaskClient) -> None:
    rv = client.get("/api-key")
    assert rv.status_code == 200
    assert b"Your account has no email address." in rv.data
    assert b'action="/account/email"' in rv.data


def test_change_email_requires_csrf_token(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    rv = client.post("/account/email", data={"email": email})
    assert rv.status_code == 400
    assert find_messages(email) == []


def test_change_email_requires_sign_in(app: Flask) -> None:
    rv = app.test_client().post("/account/email", data={"email": unique_address()})
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_change_email_rejects_invalid_address(client: FlaskClient) -> None:
    rv = request_link(client, "not an address")
    assert rv.status_code == 400
    assert b"does not look like an email address" in rv.data


def test_confirm_email(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    rv = request_link(client, email.upper())
    assert rv.status_code == 303
    assert rv.headers["Location"].endswith("/api-key")

    # The account page says where the link went, once.
    page = client.get("/api-key").data.decode()
    assert "We sent a confirmation link to " + mask_email(email) in page
    assert email not in page
    assert "We sent a confirmation link" not in client.get("/api-key").data.decode()

    # Nothing changes until the link is used.
    assert account_email(app, ACCOUNT_ID) == (None, None)

    link = link_from_mail(email)
    for _ in range(2):
        # Opening the link only shows a button; a mail scanner fetching it
        # does not use it up.
        rv = client.get(link)
        assert rv.status_code == 200
        assert email in rv.data.decode()
        assert b"Confirm this address" in rv.data
        assert rv.headers["Referrer-Policy"] == "no-referrer"
        assert rv.headers["X-Frame-Options"] == "DENY"
        assert account_email(app, ACCOUNT_ID) == (None, None)

    rv = confirm(client, link)
    assert rv.status_code == 303
    stored, verified = account_email(app, ACCOUNT_ID)
    assert stored == email
    assert verified is not None

    page = client.get("/api-key").data.decode()
    assert "Your email address is now " + mask_email(email) in page
    assert "Your account's email address is <b>" + mask_email(email) in page

    # The link works once.
    rv = confirm(client, link)
    assert rv.status_code == 400
    assert b"not valid" in rv.data
    rv = client.get(link)
    assert rv.status_code == 400


def test_confirm_requires_csrf_token(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    request_link(client, email)
    link = link_from_mail(email)
    rv = client.post("/account/email/confirm", data={"token": token_of(link)})
    assert rv.status_code == 400
    assert account_email(app, ACCOUNT_ID) == (None, None)
    # Still usable.
    assert confirm(client, link).status_code == 303


def test_confirm_link_requires_sign_in(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    request_link(client, email)
    link = link_from_mail(email)
    rv = app.test_client().get(link)
    assert rv.status_code == 302
    assert "/login" in rv.headers["Location"]


def test_confirm_link_from_another_account(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    request_link(client, email)
    link = link_from_mail(email)

    other = app.test_client()
    sign_in(other, OTHER_ACCOUNT_ID)
    rv = other.get(link)
    assert rv.status_code == 400
    assert b"different AcoustID account" in rv.data
    rv = confirm(other, link)
    assert rv.status_code == 400
    assert account_email(app, OTHER_ACCOUNT_ID) == (None, None)

    # Not used up by the wrong account.
    assert confirm(client, link).status_code == 303
    assert account_email(app, ACCOUNT_ID)[0] == email


def test_address_already_on_another_account(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    with app.acoustid_script.context() as ctx:  # type: ignore
        assert set_account_email(ctx.db.get_app_db(), OTHER_ACCOUNT_ID, email)
        ctx.db.session.commit()

    # Asking does not reveal that the address is taken.
    rv = request_link(client, email)
    assert rv.status_code == 303

    rv = confirm(client, link_from_mail(email))
    assert rv.status_code == 400
    assert b"Another AcoustID account already uses this email address" in rv.data
    assert account_email(app, ACCOUNT_ID) == (None, None)
    assert account_email(app, OTHER_ACCOUNT_ID)[0] == email


def test_same_address_again(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    request_link(client, email)
    confirm(client, link_from_mail(email))
    rv = request_link(client, email)
    assert rv.status_code == 400
    assert b"already the address on your account" in rv.data
    assert len(find_messages(email)) == 1


def test_changing_keeps_old_address_until_confirmed(
    app: Flask, client: FlaskClient
) -> None:
    old = unique_address()
    request_link(client, old)
    confirm(client, link_from_mail(old))

    new = unique_address()
    request_link(client, new)
    assert account_email(app, ACCOUNT_ID)[0] == old
    confirm(client, link_from_mail(new))
    assert account_email(app, ACCOUNT_ID)[0] == new


def test_emails_per_address_are_limited(app: Flask) -> None:
    email = unique_address()
    clients = []
    for account_id in (ACCOUNT_ID, OTHER_ACCOUNT_ID):
        c = app.test_client()
        sign_in(c, account_id)
        clients.append(c)
    for i in range(MAX_EMAILS_PER_ADDRESS_PER_HOUR):
        assert request_link(clients[i % 2], email).status_code == 303
    rv = request_link(clients[1], email)
    assert rv.status_code == 400
    assert b"Too many emails" in rv.data
    assert len(find_messages(email)) == MAX_EMAILS_PER_ADDRESS_PER_HOUR


def test_emails_per_account_are_limited(client: FlaskClient) -> None:
    for _ in range(MAX_EMAILS_PER_ACCOUNT_PER_HOUR):
        assert request_link(client, unique_address()).status_code == 303
    email = unique_address()
    rv = request_link(client, email)
    assert rv.status_code == 400
    assert b"Too many emails" in rv.data
    assert find_messages(email) == []


def test_mail_failure(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    with mock.patch.object(app.acoustid_config.mail, "host", ""):  # type: ignore
        rv = request_link(client, email)
    assert rv.status_code == 400
    assert b"could not send the email" in rv.data
    assert b"We sent" not in client.get("/api-key").data


def test_set_account_email_conflict_keeps_transaction(app: Flask) -> None:
    email = unique_address()
    with app.acoustid_script.context() as ctx:  # type: ignore
        conn = ctx.db.get_app_db()
        assert set_account_email(conn, OTHER_ACCOUNT_ID, email)
        assert not set_account_email(conn, ACCOUNT_ID, email)
        # Setting it again on the account that has it is fine.
        assert set_account_email(conn, OTHER_ACCOUNT_ID, email)
        conn.execute(sql.text("SELECT 1"))
        ctx.db.session.commit()
    assert account_email(app, ACCOUNT_ID) == (None, None)
    assert account_email(app, OTHER_ACCOUNT_ID)[0] == email
    with app.acoustid_script.context() as ctx:  # type: ignore
        found = find_account_by_email(ctx.db.get_app_db(), email)
    assert found == OTHER_ACCOUNT_ID
