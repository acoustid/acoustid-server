# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
from typing import Any, Iterator
from unittest import mock

import pytest
from sqlalchemy import sql

import tests
from acoustid import tables as schema
from acoustid.api.v2 import LookupHandlerParams
from acoustid.data import account as account_data
from acoustid.data.account import (
    USER_KEY_APPROVED,
    USER_KEY_EXPIRED,
    USER_KEY_USED_PREFIX,
    UserKey,
    approve_user_key_link_request,
    create_user_key_link_request,
    delete_abandoned_link_requests,
    lookup_user_api_key,
    mark_user_keys_used,
    record_user_key_use,
)
from acoustid.db import AppDB
from acoustid.script import ScriptContext
from acoustid.scripts.user_keys import run_flush_user_key_use
from tests import with_database, with_script_context
from tests.test_api_v2 import lookup_values

TODAY = datetime.date.today()


@pytest.fixture(autouse=True)
def clean_redis() -> Iterator[None]:
    account_data._recorded_user_key_use.clear()
    yield
    account_data._recorded_user_key_use.clear()
    assert tests.script is not None
    redis = tests.script.get_redis()
    for key in redis.scan_iter(USER_KEY_USED_PREFIX + "*"):
        redis.delete(key)


def approved_key(conn: AppDB) -> str:
    req = create_user_key_link_request(conn, 1, "nas")
    approve_user_key_link_request(conn, req.link_code, 2)
    return req.apikey


def set_key_dates(conn: AppDB, apikey: str, **values: Any) -> None:
    table = schema.account_application_key
    conn.execute(table.update().where(table.c.apikey == apikey).values(**values))


def last_used(conn: AppDB, apikey: str) -> datetime.date | None:
    table = schema.account_application_key
    query = sql.select(table.c.last_used).where(table.c.apikey == apikey)
    return conn.execute(query).scalar_one()


@with_database
def test_approved_key_lapses_a_year_after_last_use(conn: AppDB) -> None:
    apikey = approved_key(conn)
    year_ago = TODAY - datetime.timedelta(days=366)
    set_key_dates(conn, apikey, approved=year_ago, last_used=TODAY)
    assert lookup_user_api_key(conn, apikey) == UserKey(2, 1, USER_KEY_APPROVED)
    set_key_dates(conn, apikey, last_used=year_ago)
    assert lookup_user_api_key(conn, apikey) == UserKey(2, 1, USER_KEY_EXPIRED)


@with_database
def test_never_used_key_lapses_a_year_after_approval(conn: AppDB) -> None:
    apikey = approved_key(conn)
    assert lookup_user_api_key(conn, apikey) == UserKey(2, 1, USER_KEY_APPROVED)
    set_key_dates(conn, apikey, approved=TODAY - datetime.timedelta(days=366))
    assert lookup_user_api_key(conn, apikey) == UserKey(2, 1, USER_KEY_EXPIRED)


@with_database
def test_mark_user_keys_used_only_moves_forward(conn: AppDB) -> None:
    apikey = approved_key(conn)
    mark_user_keys_used(conn, [apikey], TODAY)
    mark_user_keys_used(conn, [apikey], TODAY - datetime.timedelta(days=1))
    assert last_used(conn, apikey) == TODAY


@with_database
def test_delete_abandoned_link_requests(conn: AppDB) -> None:
    old = create_user_key_link_request(conn, 1, None)
    recent = create_user_key_link_request(conn, 1, None)
    approved = create_user_key_link_request(conn, 1, None)
    approve_user_key_link_request(conn, approved.link_code, 2)
    long_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=31
    )
    for req in (old, approved):
        set_key_dates(conn, req.apikey, link_expires=long_ago)

    assert delete_abandoned_link_requests(conn) == 1
    assert lookup_user_api_key(conn, old.apikey) is None
    assert lookup_user_api_key(conn, recent.apikey) is not None
    assert lookup_user_api_key(conn, approved.apikey) is not None


def test_use_is_recorded_once_per_process_per_day() -> None:
    redis = mock.MagicMock()
    record_user_key_use(redis, "key", TODAY)
    record_user_key_use(redis, "key", TODAY)
    assert redis.pipeline.return_value.sadd.call_count == 1
    record_user_key_use(redis, "key", TODAY + datetime.timedelta(days=1))
    assert redis.pipeline.return_value.sadd.call_count == 2


def test_recording_use_never_fails_the_request() -> None:
    redis = mock.MagicMock()
    redis.pipeline.return_value.execute.side_effect = Exception("down")
    record_user_key_use(redis, "key", TODAY)
    # Not remembered as recorded, so the next request tries again.
    redis.pipeline.return_value.execute.side_effect = None
    record_user_key_use(redis, "key", TODAY)
    assert redis.pipeline.return_value.sadd.call_count == 2


@with_script_context
def test_lookup_records_linked_keys_only(ctx: ScriptContext) -> None:
    apikey = approved_key(ctx.db.get_app_db())
    for user in (apikey, "user1key"):
        params = LookupHandlerParams(ctx.config)
        params.redis = ctx.redis
        params.parse(lookup_values(user=user), ctx.db)
    used = ctx.redis.smembers(USER_KEY_USED_PREFIX + TODAY.isoformat())
    assert used == {apikey.encode()}


@with_script_context
def test_flush_writes_last_used_and_clears_redis(ctx: ScriptContext) -> None:
    apikey = approved_key(ctx.db.get_app_db())
    ctx.db.session.commit()
    try:
        record_user_key_use(ctx.redis, apikey, TODAY)
        assert tests.script is not None
        run_flush_user_key_use(tests.script)
        assert last_used(ctx.db.get_app_db(), apikey) == TODAY
        assert not ctx.redis.exists(USER_KEY_USED_PREFIX + TODAY.isoformat())
    finally:
        ctx.db.get_app_db().execute(schema.account_application_key.delete())
        ctx.db.session.commit()
