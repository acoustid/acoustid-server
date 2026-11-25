# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import json
from typing import Any, Iterator
from unittest import mock

import pytest
from sqlalchemy import sql
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

import tests
from acoustid import const
from acoustid import tables as schema
from acoustid.api.v2.misc import UserLinkStatusHandler, UserRequestLinkHandler
from acoustid.data.account import (
    USER_KEY_CACHE_PREFIX,
    USER_KEY_PENDING,
    UserKey,
    approve_user_key_link_request,
    decline_user_key_link_request,
    read_cached_user_key,
)
from acoustid.script import ScriptContext
from tests import with_script_context


@pytest.fixture(autouse=True)
def clean_redis() -> Iterator[None]:
    yield
    assert tests.script is not None
    redis = tests.script.get_redis()
    for pattern in ("linkreq:*", USER_KEY_CACHE_PREFIX + "*"):
        for key in redis.scan_iter(pattern):
            redis.delete(key)


def call(
    handler_class: Any,
    ctx: ScriptContext,
    headers: list[tuple[str, str]] | None = None,
    **values: str,
) -> tuple[int, dict[str, Any]]:
    data = {"format": "json", "client": "app1key"}
    data.update(values)
    builder = EnvironBuilder(method="POST", data=data, headers=headers)
    resp = handler_class(ctx).handle(Request(builder.get_environ()))
    return resp.status_code, json.loads(resp.data)


def request_link(ctx: ScriptContext, **values: str) -> tuple[int, dict[str, Any]]:
    return call(UserRequestLinkHandler, ctx, None, **values)


def link_status(ctx: ScriptContext, apikey: str) -> dict[str, Any]:
    status, data = call(UserLinkStatusHandler, ctx, user=apikey)
    assert status == 200, data
    return data["key"]


def expire_link_requests(ctx: ScriptContext) -> None:
    ctx.db.get_app_db().execute(
        sql.text(
            "UPDATE account_application_key SET link_expires = now() - interval '1 second'"
        )
    )
    ctx.db.session.commit()


@with_script_context
def test_request_link(ctx: ScriptContext) -> None:
    status, data = request_link(
        ctx, device="nas", return_url="http://192.168.1.10:8095/settings"
    )
    assert status == 200, data
    apikey = data["user"]["apikey"]
    link = data["user"]["link"]
    assert len(link["code"]) == 9 and link["code"][4] == "-"
    base_url = ctx.config.website.base_url.rstrip("/")
    assert link["url"] == base_url + "/link?code=" + link["code"]
    assert link["expires"]

    table = schema.account_application_key
    row = (
        ctx.db.get_app_db()
        .execute(sql.select(table).where(table.c.apikey == apikey))
        .one()
    )
    assert row.application_id == 1
    assert row.device == "nas"
    assert row.return_url == "http://192.168.1.10:8095/settings"

    # Cached as pending straight away, so a lookup that reaches a replica
    # before the new row does is not remembered as an unknown key.
    assert read_cached_user_key(ctx.redis, apikey) == (
        True,
        UserKey(None, 1, USER_KEY_PENDING, row.id),
    )


INVALID_LINK_PARAMETERS = [
    ("return_url", "javascript:alert(1)"),
    ("return_url", "ftp://example.com/"),
    ("return_url", "http:///no-host"),
    ("return_url", "http://example.com/" + "x" * 2000),
    ("return_url", "http://evil.example\\@acoustid.org/"),
    ("return_url", "http://acoustid.org@evil.example/"),
    ("return_url", "http://user:pass@example.com/"),
    ("return_url", "http://ex\nample.com/"),
    ("return_url", "http://example.com/a b"),
    ("return_url", "http://exa\u202emple.com/"),
    ("device", "x" * 101),
    ("device", "nas\u202egnp.exe"),
    ("device", "line\nbreak"),
]


@with_script_context
def test_request_link_rejects_invalid_parameters(ctx: ScriptContext) -> None:
    for name, value in INVALID_LINK_PARAMETERS:
        status, data = request_link(ctx, **{name: value})
        assert status == 400, (name, value)
        assert data["error"]["code"] == 20
        assert name in data["error"]["message"]


@with_script_context
def test_request_link_accepts_local_addresses(ctx: ScriptContext) -> None:
    for url in [
        "http://192.168.1.10:8095/",
        "http://[fd00::1]:8095/settings?tab=providers#acoustid",
        "https://music.example.home/",
    ]:
        status, data = request_link(ctx, return_url=url, device="Kitchen NAS")
        assert status == 200, (url, data)


@with_script_context
def test_request_link_is_limited_per_ip(ctx: ScriptContext) -> None:
    for _ in range(const.USER_KEY_LINK_REQUESTS_PER_IP_PER_HOUR):
        status, data = request_link(ctx)
        assert status == 200, data
    status, data = request_link(ctx)
    assert status == 429
    assert data["error"]["code"] == 14


@with_script_context
def test_pending_cap_per_application_clears_as_codes_expire(
    ctx: ScriptContext,
) -> None:
    with mock.patch.object(const, "USER_KEY_MAX_PENDING_LINKS_PER_APPLICATION", 2):
        assert request_link(ctx)[0] == 200
        assert request_link(ctx)[0] == 200
        status, data = request_link(ctx)
        assert status == 429
        assert data["error"]["code"] == 14

        # Other applications are not affected.
        assert request_link(ctx, client="app2key")[0] == 200

        expire_link_requests(ctx)
        assert request_link(ctx)[0] == 200


@with_script_context
def test_link_status(ctx: ScriptContext) -> None:
    _, data = request_link(ctx)
    apikey = data["user"]["apikey"]
    code = data["user"]["link"]["code"]

    key = link_status(ctx, apikey)
    assert key["state"] == "pending"
    assert key["expires"] == data["user"]["link"]["expires"]

    assert approve_user_key_link_request(ctx.db.get_app_db(), code, 2) == apikey
    ctx.db.session.commit()
    assert link_status(ctx, apikey) == {"state": "approved"}


@with_script_context
def test_link_status_of_declined_and_expired_requests(ctx: ScriptContext) -> None:
    _, declined = request_link(ctx)
    decline_user_key_link_request(ctx.db.get_app_db(), declined["user"]["link"]["code"])
    ctx.db.session.commit()
    assert link_status(ctx, declined["user"]["apikey"]) == {"state": "declined"}

    _, expired = request_link(ctx)
    expire_link_requests(ctx)
    assert link_status(ctx, expired["user"]["apikey"]) == {"state": "expired"}


@with_script_context
def test_link_status_of_other_keys(ctx: ScriptContext) -> None:
    assert link_status(ctx, "user1key") == {"state": "approved"}
    assert link_status(ctx, "no-such-key") == {"state": "unknown"}


@with_script_context
def test_link_status_takes_the_key_from_a_header(ctx: ScriptContext) -> None:
    status, data = call(
        UserLinkStatusHandler, ctx, headers=[("Acoustid-User-Key", "user1key")]
    )
    assert status == 200, data
    assert data["key"] == {"state": "approved"}
