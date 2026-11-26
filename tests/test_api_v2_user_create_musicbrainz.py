# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import json
import logging
from typing import Any, Iterator
from unittest import mock

import pytest
import requests
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

import tests
from acoustid import tables as schema
from acoustid.api import errors
from acoustid.api.v2.misc import UserCreateMusicBrainzHandler
from acoustid.script import ScriptContext
from tests import prepare_databases


@pytest.fixture
def ctx() -> Iterator[ScriptContext]:
    assert tests.script is not None
    with tests.script.context() as c:
        prepare_databases(c.db)
        c.db.session.commit()
    with tests.script.context() as c:
        try:
            yield c
        finally:
            c.db.session.rollback()


def userinfo(status: int, body: bytes) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = body
    return resp


def create(ctx: ScriptContext, resp: requests.Response) -> tuple[int, dict[str, Any]]:
    builder = EnvironBuilder(
        method="POST",
        base_url="https://api.acoustid.org/",
        data={"format": "json", "access_token": "SECRET-TOKEN"},
    )
    with mock.patch("acoustid.api.v2.misc.requests.get", return_value=resp):
        r = UserCreateMusicBrainzHandler(ctx).handle(Request(builder.get_environ()))
    return r.status_code, json.loads(r.data)


@pytest.mark.parametrize(
    "body",
    [
        b"<html>Service Unavailable</html>",
        b"",
        b"{}",
        b'{"error": "invalid_token", "access_token": "SECRET-TOKEN"}',
        b'{"sub": ""}',
        b'{"sub": 123}',
        b'["sub"]',
        b'"sub"',
    ],
)
def test_malformed_userinfo_is_an_invalid_token(
    ctx: ScriptContext, caplog: pytest.LogCaptureFixture, body: bytes
) -> None:
    with caplog.at_level(logging.DEBUG):
        status, data = create(ctx, userinfo(200, body))
    assert status == 400, data
    assert data["error"]["code"] == errors.ERROR_INVALID_MUSICBRAINZ_ACCESS_TOKEN
    # The caller caused it: not a server error, and the token stays out of logs.
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert "SECRET-TOKEN" not in caplog.text


def test_rejected_token_is_an_invalid_token(ctx: ScriptContext) -> None:
    status, data = create(ctx, userinfo(401, b'{"error": "invalid_token"}'))
    assert status == 400, data
    assert data["error"]["code"] == errors.ERROR_INVALID_MUSICBRAINZ_ACCESS_TOKEN


def test_valid_userinfo_creates_the_account_once(ctx: ScriptContext) -> None:
    status, data = create(ctx, userinfo(200, b'{"sub": "mb-api-user"}'))
    assert status == 200, data
    apikey = data["user"]["apikey"]
    try:
        status, data = create(ctx, userinfo(200, b'{"sub": "mb-api-user"}'))
        assert status == 200, data
        assert data["user"]["apikey"] == apikey
    finally:
        ctx.db.get_app_db().execute(
            schema.account.delete().where(schema.account.c.mbuser == "mb-api-user")
        )
        ctx.db.session.commit()
