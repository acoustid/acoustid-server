# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import os
from configparser import RawConfigParser
from typing import Any, Iterator
from unittest import mock

import pytest
from flask import Flask

from acoustid import tables as schema
from acoustid.config import MailConfig
from acoustid.data.email import (
    MAX_EMAILS_PER_IP_PER_HOUR,
    RATE_LIMIT_PREFIX,
    within_global_limits,
)
from tests.test_mail import find_messages
from tests.test_web_signin import request_signin, unique_address


@pytest.fixture()
def app(config_file: str) -> Iterator[Flask]:
    from tests import make_web_application

    app = make_web_application(config_file)
    app.config["TESTING"] = True
    yield app
    script = app.acoustid_script  # type: ignore
    with script.context() as ctx:
        conn = ctx.db.get_app_db()
        conn.execute(schema.account_email_signin.delete())
        conn.execute(schema.account_email_confirmation.delete())
        ctx.db.session.commit()
        for key in ctx.redis.scan_iter(RATE_LIMIT_PREFIX + "*"):
            ctx.redis.delete(key)


def caps(app: Flask, per_hour: int = 0, per_day: int = 0) -> Any:
    mail = app.acoustid_config.mail  # type: ignore
    return mock.patch.multiple(mail, max_per_hour=per_hour, max_per_day=per_day)


def confirm_request(app: Flask, email: str) -> int:
    client = app.test_client()
    with client.session_transaction() as flask_session:
        flask_session["id"] = 2
    client.get("/api-key")
    with client.session_transaction() as flask_session:
        token = flask_session["api_key_csrf_token"]
    rv = client.post("/account/email", data={"csrf_token": token, "email": email})
    return rv.status_code


def test_hourly_cap_covers_all_kinds_of_mail(
    app: Flask, caplog: pytest.LogCaptureFixture
) -> None:
    addresses = [unique_address() for _ in range(4)]
    with caps(app, per_hour=3):
        assert request_signin(app.test_client(), addresses[0]).status_code == 303
        assert confirm_request(app, addresses[1]) == 303
        assert request_signin(app.test_client(), addresses[2]).status_code == 303
        # The fourth email of the hour, of either kind, is refused.
        rv = request_signin(app.test_client(), addresses[3])
        assert rv.status_code == 400
        assert b"Too many emails" in rv.data
        assert confirm_request(app, addresses[3]) == 400
    assert find_messages(addresses[3]) == []
    assert caplog.text.count("Site-wide email cap reached") == 1


def test_daily_cap(app: Flask) -> None:
    with caps(app, per_day=2):
        assert request_signin(app.test_client(), unique_address()).status_code == 303
        assert request_signin(app.test_client(), unique_address()).status_code == 303
        email = unique_address()
        assert request_signin(app.test_client(), email).status_code == 400
    assert find_messages(email) == []


def test_refused_requests_do_not_use_the_cap_up(app: Flask) -> None:
    # Requests stopped by the per-address limit (in Postgres, before any
    # redis counter) send nothing, so they must not count against the
    # site-wide cap either. The per-IP test below covers a redis limit.
    email = unique_address()
    with caps(app, per_hour=4):
        for _ in range(3):
            assert request_signin(app.test_client(), email).status_code == 303
        for _ in range(5):
            assert request_signin(app.test_client(), email).status_code == 400
        assert request_signin(app.test_client(), unique_address()).status_code == 303


def test_no_cap_by_default(app: Flask) -> None:
    with caps(app):
        for _ in range(5):
            assert (
                request_signin(app.test_client(), unique_address()).status_code == 303
            )
    redis = app.acoustid_script.get_redis()  # type: ignore
    assert list(redis.scan_iter(RATE_LIMIT_PREFIX + "global:*")) == []


def test_cap_keys_expire(app: Flask) -> None:
    redis = app.acoustid_script.get_redis()  # type: ignore
    assert within_global_limits(redis, 10, 100)
    ttls = {
        key.decode().split(":")[2]: redis.ttl(key)
        for key in redis.scan_iter(RATE_LIMIT_PREFIX + "global:*")
    }
    assert set(ttls) == {"hour", "day"}
    assert 0 < ttls["hour"] <= 3600
    assert 3600 < ttls["day"] <= 86400


def test_mail_config_caps() -> None:
    parser = RawConfigParser()
    parser.read_string("[mail]\nmax_per_hour=200\nmax_per_day=2000\n")
    config = MailConfig()
    config.read(parser, "mail")
    assert (config.max_per_hour, config.max_per_day) == (200, 2000)
    env = {"X_MAIL_MAX_PER_HOUR": "50", "X_MAIL_MAX_PER_DAY": "500"}
    with mock.patch.dict(os.environ, env):
        config.read_env("X_")
    assert (config.max_per_hour, config.max_per_day) == (50, 500)
    config.validate()
    config.max_per_day = -1
    with pytest.raises(ValueError):
        config.validate()


def signin_from(app: Flask, ip: str, email: str) -> int:
    client = app.test_client()
    client.get("/login", environ_overrides={"REMOTE_ADDR": ip})
    with client.session_transaction() as flask_session:
        token = flask_session["api_key_csrf_token"]
    rv = client.post(
        "/login/email",
        data={"csrf_token": token, "email": email},
        environ_overrides={"REMOTE_ADDR": ip},
    )
    return rv.status_code


def test_requests_refused_per_ip_do_not_use_the_cap_up(app: Flask) -> None:
    with caps(app, per_hour=MAX_EMAILS_PER_IP_PER_HOUR + 1):
        for _ in range(MAX_EMAILS_PER_IP_PER_HOUR):
            assert signin_from(app, "192.0.2.1", unique_address()) == 303
        for _ in range(5):
            assert signin_from(app, "192.0.2.1", unique_address()) == 400
        # One email left under the cap, for someone else.
        assert signin_from(app, "192.0.2.2", unique_address()) == 303
        assert signin_from(app, "192.0.2.3", unique_address()) == 400


def test_hourly_refusals_do_not_count_towards_the_day(
    app: Flask, caplog: pytest.LogCaptureFixture
) -> None:
    redis = app.acoustid_script.get_redis()  # type: ignore
    results = [within_global_limits(redis, 2, 5) for _ in range(6)]
    assert results == [True, True, False, False, False, False]
    [day_key] = redis.scan_iter(RATE_LIMIT_PREFIX + "global:day:*")
    assert int(redis.get(day_key)) == 2
    assert "global:day" not in caplog.text
