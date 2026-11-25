# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import re
import threading
import time
import uuid
from typing import Any, Iterator
from unittest import mock
from urllib.parse import urlparse

import pytest
from flask import Flask
from flask.testing import FlaskClient
from redis.exceptions import RedisError
from sqlalchemy import sql

from acoustid import tables as schema
from acoustid.data.email import (
    EMAIL_ACCOUNT_NAME,
    MAX_CODE_ATTEMPTS,
    MAX_EMAILS_PER_ADDRESS_PER_HOUR,
    MAX_SIGNINS_PER_ADDRESS_PER_HOUR,
    MAX_WRONG_CODES_PER_ADDRESS_PER_DAY,
    RATE_LIMIT_PREFIX,
    create_email_signin,
    find_account_by_email,
    find_or_create_email_account,
    mask_email,
    set_account_email,
    signin_allowed,
    wrong_codes_today,
)
from acoustid.scripts.user_keys import run_cleanup_user_keys
from tests import make_web_application
from tests.test_mail import find_messages, get_message

EXISTING_ACCOUNT_ID = 2


@pytest.fixture()
def app(config_file: str) -> Iterator[Flask]:
    app = make_web_application(config_file)
    app.config["TESTING"] = True
    yield app
    script = app.acoustid_script  # type: ignore
    with script.context() as ctx:
        conn = ctx.db.get_app_db()
        conn.execute(schema.account_email_signin.delete())
        conn.execute(schema.account.delete().where(schema.account.c.id > 2))
        conn.execute(schema.account.update().values(email=None, email_verified=None))
        ctx.db.session.commit()
        for key in ctx.redis.scan_iter(RATE_LIMIT_PREFIX + "*"):
            ctx.redis.delete(key)


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()


def unique_address() -> str:
    return "test-%s@example.com" % uuid.uuid4().hex


def csrf_token(client: FlaskClient) -> str:
    with client.session_transaction() as flask_session:
        token = flask_session.get("api_key_csrf_token")
    if token is None:
        client.get("/login")
        with client.session_transaction() as flask_session:
            token = flask_session["api_key_csrf_token"]
    return token


def request_signin(
    client: FlaskClient, email: str, return_url: str | None = None
) -> Any:
    data = {"csrf_token": csrf_token(client), "email": email}
    if return_url is not None:
        data["return_url"] = return_url
    return client.post("/login/email", data=data)


def read_mail(email: str, latest: bool = False) -> tuple[str, str]:
    """The link path and the code from the email sent to the address."""
    messages = find_messages(email)
    if latest:
        summary = messages[0]
    else:
        [summary] = messages
    message = get_message(summary["ID"])
    assert message["Subject"] == "Sign in to AcoustID"
    link = re.search(r"https?://\S+/login/email/link\?token=\S+", message["Text"])
    code = re.search(r"Your code is: (\d{6})", message["Text"])
    assert link is not None and code is not None
    assert link.group(0).startswith("http://acoustid.org/")
    assert link.group(0) in message["HTML"]
    assert code.group(1) in message["HTML"]
    url = urlparse(link.group(0))
    return url.path + "?" + url.query, code.group(1)


def token_of(link: str) -> str:
    return link.split("token=", 1)[1]


def enter_code(client: FlaskClient, code: str) -> Any:
    return client.post(
        "/login/email/code", data={"csrf_token": csrf_token(client), "code": code}
    )


def use_link(client: FlaskClient, link: str) -> Any:
    client.get(link)
    return client.post(
        "/login/email/link",
        data={"csrf_token": csrf_token(client), "token": token_of(link)},
    )


def signed_in_as(client: FlaskClient) -> int | None:
    with client.session_transaction() as flask_session:
        return flask_session.get("id")


def account(app: Flask, account_id: int) -> Any:
    with app.acoustid_script.context() as ctx:  # type: ignore
        table = schema.account
        return (
            ctx.db.get_app_db()
            .execute(sql.select(table).where(table.c.id == account_id))
            .one()
        )


def give_email(app: Flask, account_id: int, email: str) -> None:
    with app.acoustid_script.context() as ctx:  # type: ignore
        assert set_account_email(ctx.db.get_app_db(), account_id, email)
        ctx.db.session.commit()


def signin_rows(app: Flask) -> list[Any]:
    with app.acoustid_script.context() as ctx:  # type: ignore
        table = schema.account_email_signin
        return list(ctx.db.get_app_db().execute(sql.select(table)).fetchall())


def expire_signins(app: Flask) -> None:
    with app.acoustid_script.context() as ctx:  # type: ignore
        table = schema.account_email_signin
        ctx.db.get_app_db().execute(
            table.update().values(expires=sql.func.now() - sql.text("interval '1 s'"))
        )
        ctx.db.session.commit()


def test_login_page_has_email_form(client: FlaskClient) -> None:
    rv = client.get("/login")
    assert rv.status_code == 200
    assert b'action="/login/email"' in rv.data
    assert b"Email me a sign-in link" in rv.data


def test_request_requires_csrf_token(client: FlaskClient) -> None:
    email = unique_address()
    rv = client.post("/login/email", data={"email": email})
    assert rv.status_code == 400
    assert find_messages(email) == []


def test_request_rejects_invalid_address(client: FlaskClient) -> None:
    rv = request_signin(client, "not an address")
    assert rv.status_code == 400
    assert b"does not look like an email address" in rv.data


def test_new_account_by_code(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    rv = request_signin(client, email.upper())
    assert rv.status_code == 303
    assert rv.headers["Location"].endswith("/login/email/code")

    page = client.get("/login/email/code")
    assert page.status_code == 200
    assert mask_email(email) in page.data.decode()
    assert email not in page.data.decode()

    _, code = read_mail(email)
    rv = enter_code(client, code)
    assert rv.status_code == 303
    assert rv.headers["Location"].endswith("/api-key")

    account_id = signed_in_as(client)
    assert account_id is not None and account_id > 2
    row = account(app, account_id)
    assert row.email == email
    assert row.email_verified is not None
    assert row.name == EMAIL_ACCOUNT_NAME
    assert row.apikey
    # Kept, marked used, for the per-address limits.
    [request] = signin_rows(app)
    assert request.used is not None


def test_existing_account_by_code(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    give_email(app, EXISTING_ACCOUNT_ID, email)
    request_signin(client, email)
    _, code = read_mail(email)
    assert enter_code(client, code).status_code == 303
    assert signed_in_as(client) == EXISTING_ACCOUNT_ID


def test_same_answer_with_and_without_account(app: Flask) -> None:
    known = unique_address()
    give_email(app, EXISTING_ACCOUNT_ID, known)
    unknown = unique_address()
    answers = []
    for email in (known, unknown):
        rv = request_signin(app.test_client(), email)
        answers.append((rv.status_code, rv.headers["Location"]))
        assert len(find_messages(email)) == 1
    assert answers[0] == answers[1]


def test_code_with_spaces(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    request_signin(client, email)
    _, code = read_mail(email)
    assert enter_code(client, " %s %s " % (code[:3], code[3:])).status_code == 303
    assert signed_in_as(client) is not None


def test_code_only_works_in_the_browser_that_asked(
    app: Flask, client: FlaskClient
) -> None:
    email = unique_address()
    request_signin(client, email)
    _, code = read_mail(email)
    other = app.test_client()
    rv = enter_code(other, code)
    assert rv.status_code == 302
    assert rv.headers["Location"].endswith("/login")
    assert signed_in_as(other) is None
    assert enter_code(client, code).status_code == 303


def test_wrong_codes_kill_the_request(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    request_signin(client, email)
    link, code = read_mail(email)
    wrong = "%06d" % ((int(code) + 1) % 1000000)
    for _ in range(MAX_CODE_ATTEMPTS - 1):
        rv = enter_code(client, wrong)
        assert rv.status_code == 400
        assert b"That code is not right" in rv.data
    rv = enter_code(client, wrong)
    assert rv.status_code == 400
    assert b"too many wrong codes" in rv.data
    # Dead: neither the right code nor the link works any more.
    rv = enter_code(client, code)
    assert rv.status_code == 400
    assert b"Ask for a new email" in rv.data
    assert signed_in_as(client) is None
    rv = use_link(app.test_client(), link)
    assert rv.status_code == 400
    assert b"not valid" in rv.data


def test_wrong_code_then_right_code(client: FlaskClient) -> None:
    email = unique_address()
    request_signin(client, email)
    _, code = read_mail(email)
    wrong = "%06d" % ((int(code) + 1) % 1000000)
    assert enter_code(client, wrong).status_code == 400
    assert enter_code(client, code).status_code == 303


def test_link_in_another_browser(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    request_signin(client, email)
    link, code = read_mail(email)

    other = app.test_client()
    for _ in range(2):
        # Opening the link only shows a button.
        rv = other.get(link)
        assert rv.status_code == 200
        assert mask_email(email) in rv.data.decode()
        assert email not in rv.data.decode()
        assert rv.headers["Referrer-Policy"] == "no-referrer"
        assert rv.headers["X-Frame-Options"] == "DENY"
        assert signed_in_as(other) is None
    assert len(signin_rows(app)) == 1

    rv = other.post(
        "/login/email/link",
        data={"csrf_token": csrf_token(other), "token": token_of(link)},
    )
    assert rv.status_code == 303
    assert signed_in_as(other) is not None

    # The link used the code up too, and works once.
    rv = enter_code(client, code)
    assert rv.status_code == 400
    assert b"Ask for a new email" in rv.data
    assert signed_in_as(client) is None
    rv = use_link(app.test_client(), link)
    assert rv.status_code == 400


def test_link_requires_csrf_token(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    request_signin(client, email)
    link, _ = read_mail(email)
    other = app.test_client()
    rv = other.post("/login/email/link", data={"token": token_of(link)})
    assert rv.status_code == 400
    assert signed_in_as(other) is None
    assert use_link(other, link).status_code == 303


def test_expired_request(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    request_signin(client, email)
    link, code = read_mail(email)
    expire_signins(app)
    rv = enter_code(client, code)
    assert rv.status_code == 400
    assert b"Ask for a new email" in rv.data
    assert signed_in_as(client) is None
    assert client.get(link).status_code == 400
    assert use_link(client, link).status_code == 400


def test_code_page_after_expiry(app: Flask, client: FlaskClient) -> None:
    request_signin(client, unique_address())
    expire_signins(app)
    rv = client.get("/login/email/code")
    assert rv.status_code == 400
    assert b"Ask for a new email" in rv.data


def test_code_page_without_request(client: FlaskClient) -> None:
    rv = client.get("/login/email/code")
    assert rv.status_code == 302
    assert rv.headers["Location"].endswith("/login")


@pytest.mark.parametrize(
    "return_url,expected",
    [
        ("http://localhost/track/x", "http://localhost/track/x"),
        ("https://evil.example/x", "/api-key"),
    ],
)
def test_return_url(
    app: Flask, client: FlaskClient, return_url: str, expected: str
) -> None:
    email = unique_address()
    request_signin(client, email, return_url)
    link, _ = read_mail(email)
    rv = use_link(app.test_client(), link)
    assert rv.status_code == 303
    assert rv.headers["Location"].endswith(expected)


def test_signed_in_user_is_sent_home(app: Flask, client: FlaskClient) -> None:
    token = csrf_token(client)
    with client.session_transaction() as flask_session:
        flask_session["id"] = EXISTING_ACCOUNT_ID
    email = unique_address()
    rv = client.post("/login/email", data={"csrf_token": token, "email": email})
    assert rv.status_code == 302
    assert find_messages(email) == []


def test_emails_per_address_are_limited(app: Flask) -> None:
    email = unique_address()
    for _ in range(MAX_EMAILS_PER_ADDRESS_PER_HOUR):
        assert request_signin(app.test_client(), email).status_code == 303
    rv = request_signin(app.test_client(), email)
    assert rv.status_code == 400
    assert b"Too many emails" in rv.data
    assert len(find_messages(email)) == MAX_EMAILS_PER_ADDRESS_PER_HOUR


def test_address_limit_is_shared_with_confirmation_emails(app: Flask) -> None:
    email = unique_address()
    confirming = app.test_client()
    with confirming.session_transaction() as flask_session:
        flask_session["id"] = EXISTING_ACCOUNT_ID
    confirming.get("/api-key")
    with confirming.session_transaction() as flask_session:
        token = flask_session["api_key_csrf_token"]
    for _ in range(MAX_EMAILS_PER_ADDRESS_PER_HOUR):
        rv = confirming.post(
            "/account/email", data={"csrf_token": token, "email": email}
        )
        assert rv.status_code == 303
    rv = request_signin(app.test_client(), email)
    assert rv.status_code == 400
    assert b"Too many emails" in rv.data


def test_mail_failure(app: Flask, client: FlaskClient) -> None:
    with mock.patch.object(app.acoustid_config.mail, "host", ""):  # type: ignore
        rv = request_signin(client, unique_address())
    assert rv.status_code == 400
    assert b"could not send the email" in rv.data
    assert client.get("/login/email/code").status_code == 302


def age_signins(app: Flask, interval: str) -> None:
    with app.acoustid_script.context() as ctx:  # type: ignore
        table = schema.account_email_signin
        ctx.db.get_app_db().execute(
            table.update().values(
                created=table.c.created - sql.text("interval '%s'" % interval),
                expires=table.c.expires - sql.text("interval '%s'" % interval),
            )
        )
        ctx.db.session.commit()


def test_cleanup_deletes_old_signins(app: Flask, client: FlaskClient) -> None:
    # Kept for a day after they are made, for the per-address limits.
    request_signin(client, unique_address())
    age_signins(app, "23 hours")
    run_cleanup_user_keys(app.acoustid_script)  # type: ignore
    assert len(signin_rows(app)) == 1
    age_signins(app, "2 hours")
    live = unique_address()
    request_signin(app.test_client(), live)
    run_cleanup_user_keys(app.acoustid_script)  # type: ignore
    assert [row.email for row in signin_rows(app)] == [live]


def test_only_hashes_are_stored(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    request_signin(client, email)
    link, code = read_mail(email)
    [row] = signin_rows(app)
    assert token_of(link) not in str(tuple(row))
    assert row.code_hash != code
    assert code not in row.code_hash


def test_account_created_concurrently(app: Flask) -> None:
    # Another request made the account between the lookup and the insert:
    # the unique index refuses the second, and its account is not left behind.
    email = unique_address()
    give_email(app, EXISTING_ACCOUNT_ID, email)
    with app.acoustid_script.context() as ctx:  # type: ignore
        conn = ctx.db.get_app_db()
        before = conn.execute(sql.select(sql.func.max(schema.account.c.id))).scalar()
        real_find = find_account_by_email
        calls = []

        def find(conn: Any, email: str) -> int | None:
            calls.append(email)
            return None if len(calls) == 1 else real_find(conn, email)

        with mock.patch("acoustid.data.email.find_account_by_email", find):
            account_id = find_or_create_email_account(conn, email, "127.0.0.1")
        ctx.db.session.commit()
        conn = ctx.db.get_app_db()
        after = conn.execute(sql.select(sql.func.max(schema.account.c.id))).scalar()
    assert account_id == EXISTING_ACCOUNT_ID
    assert after == before


def test_code_requires_csrf_token(client: FlaskClient) -> None:
    email = unique_address()
    request_signin(client, email)
    _, code = read_mail(email)
    rv = client.post("/login/email/code", data={"code": code})
    assert rv.status_code == 400
    assert signed_in_as(client) is None
    assert enter_code(client, code).status_code == 303


def wrong(code: str) -> str:
    return "%06d" % ((int(code) + 1) % 1000000)


def test_address_limit_holds_without_redis(app: Flask) -> None:
    email = unique_address()
    with mock.patch("redis.client.Pipeline.execute", side_effect=RedisError("gone")):
        for _ in range(MAX_SIGNINS_PER_ADDRESS_PER_HOUR):
            assert request_signin(app.test_client(), email).status_code == 303
        rv = request_signin(app.test_client(), email)
    assert rv.status_code == 400
    assert b"Too many emails" in rv.data
    assert len(find_messages(email)) == MAX_SIGNINS_PER_ADDRESS_PER_HOUR


def test_wrong_codes_per_address_per_day(app: Flask) -> None:
    email = unique_address()
    # One short of killing each request, so the last one is still alive.
    per_request = MAX_CODE_ATTEMPTS - 1
    wrong_so_far = 0
    with mock.patch("redis.client.Pipeline.execute", side_effect=RedisError("gone")):
        while wrong_so_far < MAX_WRONG_CODES_PER_ADDRESS_PER_DAY:
            # A new hour's worth of emails each time round.
            age_signins(app, "61 minutes")
            client = app.test_client()
            assert request_signin(client, email).status_code == 303
            link, code = read_mail(email, latest=True)
            for _ in range(
                min(per_request, MAX_WRONG_CODES_PER_ADDRESS_PER_DAY - wrong_so_far)
            ):
                assert enter_code(client, wrong(code)).status_code == 400
                wrong_so_far += 1
    # Codes are refused now, the right one too, but the link still works.
    rv = enter_code(client, code)
    assert rv.status_code == 400
    assert b"Too many wrong codes for this address today" in rv.data
    assert signed_in_as(client) is None
    assert use_link(app.test_client(), link).status_code == 303


def test_code_from_an_earlier_email(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    request_signin(client, email)
    _, first_code = read_mail(email)
    request_signin(client, email)
    rv = enter_code(client, first_code)
    assert rv.status_code == 303
    assert signed_in_as(client) is not None
    # Both requests are used up.
    rows = signin_rows(app)
    assert len(rows) == 2
    assert all(row.used is not None for row in rows)


def test_second_click_does_not_sign_out(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    request_signin(client, email)
    _, code = read_mail(email)
    token = csrf_token(client)
    # Two submissions sent with the same cookie: the second arrives after
    # the first has signed in, and must not send back a session of its own.
    second = app.test_client()
    cookie = client.get_cookie("session")
    assert cookie is not None
    second.set_cookie("session", cookie.value)
    assert enter_code(client, code).status_code == 303
    rv = second.post("/login/email/code", data={"csrf_token": token, "code": code})
    assert rv.status_code == 400
    assert "Set-Cookie" not in rv.headers


def test_signing_in_starts_a_new_session(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    request_signin(client, email)
    before = csrf_token(client)
    _, code = read_mail(email)
    enter_code(client, code)
    with client.session_transaction() as flask_session:
        assert set(flask_session.keys()) == {"id"}
        assert before not in flask_session.values()


def test_link_page_warns_when_signed_in(app: Flask, client: FlaskClient) -> None:
    email = unique_address()
    request_signin(client, email)
    link, _ = read_mail(email)
    other = app.test_client()
    with other.session_transaction() as flask_session:
        flask_session["id"] = EXISTING_ACCOUNT_ID
    rv = other.get(link)
    assert b"You are signed in to an AcoustID account already" in rv.data
    rv = app.test_client().get(link)
    assert b"You are signed in" not in rv.data


def test_used_requests_still_count_against_the_address(app: Flask) -> None:
    email = unique_address()
    with mock.patch("redis.client.Pipeline.execute", side_effect=RedisError("gone")):
        for _ in range(MAX_SIGNINS_PER_ADDRESS_PER_HOUR):
            client = app.test_client()
            request_signin(client, email)
            _, code = read_mail(email, latest=True)
            assert enter_code(client, wrong(code)).status_code == 400
            assert enter_code(client, code).status_code == 303
        rv = request_signin(app.test_client(), email)
    assert rv.status_code == 400
    assert b"Too many emails" in rv.data
    with app.acoustid_script.context() as ctx:  # type: ignore
        assert wrong_codes_today(ctx.db.get_app_db(), email) == 3


def test_codes_are_only_tried_for_the_newest_address(app: Flask) -> None:
    victim = unique_address()
    attacker = unique_address()
    client = app.test_client()
    request_signin(client, victim)
    _, victim_code = read_mail(victim)
    with client.session_transaction() as flask_session:
        victim_ids = list(flask_session["email_signin_ids"])
    request_signin(client, attacker)
    with client.session_transaction() as flask_session:
        # A new address starts a new list.
        assert victim_ids[0] not in flask_session["email_signin_ids"]
        # Even a session made to hold both only tries the newest address.
        flask_session["email_signin_ids"] = (
            victim_ids + flask_session["email_signin_ids"]
        )
    rv = enter_code(client, victim_code)
    assert rv.status_code == 400
    assert signed_in_as(client) is None
    with app.acoustid_script.context() as ctx:  # type: ignore
        conn = ctx.db.get_app_db()
        assert wrong_codes_today(conn, victim) == 0
        assert wrong_codes_today(conn, attacker) == 1


def test_concurrent_requests_cannot_both_pass_the_limit(app: Flask) -> None:
    email = unique_address()
    for _ in range(MAX_SIGNINS_PER_ADDRESS_PER_HOUR - 1):
        request_signin(app.test_client(), email)
    script = app.acoustid_script  # type: ignore
    first_holds_lock = threading.Event()
    results: dict[str, bool] = {}

    def first() -> None:
        with script.context() as ctx:
            conn = ctx.db.get_app_db()
            results["first"] = signin_allowed(conn, email)
            first_holds_lock.set()
            time.sleep(0.5)
            create_email_signin(conn, "secret", email, None)
            ctx.db.session.commit()

    def second() -> None:
        first_holds_lock.wait()
        with script.context() as ctx:
            results["second"] = signin_allowed(ctx.db.get_app_db(), email)
            ctx.db.session.rollback()

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert results == {"first": True, "second": False}
