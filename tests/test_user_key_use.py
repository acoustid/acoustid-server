# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
from typing import Any, Iterator, NamedTuple

import pytest
from sqlalchemy import sql
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

import tests
from acoustid import const
from acoustid import tables as schema
from acoustid.api.v2 import LookupHandler, LookupHandlerParams, SubmitHandler
from acoustid.data.account import (
    USER_KEY_APPROVED,
    USER_KEY_EXPIRED,
    UserKey,
    approve_user_key_link_request,
    create_user_key_link_request,
    delete_abandoned_link_requests,
    lookup_user_api_key,
    mark_user_key_used,
)
from acoustid.data.stats import (
    NUM_PARTITIONS,
    USER_STATS_ROOT_KEY,
    UserStatsKey,
    pack_user_stats_key,
    unpack_user_stats_key,
    update_user_counter,
)
from acoustid.db import AppDB
from acoustid.script import ScriptContext
from acoustid.scripts.user_keys import run_cleanup_user_keys, run_update_user_stats
from tests import with_database, with_script_context
from tests.test_api_v2 import TEST_1_FP, TEST_1_LENGTH, lookup_values

TODAY = datetime.date.today()
YEAR_AGO = TODAY - datetime.timedelta(days=366)


@pytest.fixture(autouse=True)
def clean_redis() -> Iterator[None]:
    yield
    assert tests.script is not None
    redis = tests.script.get_redis()
    for key in redis.scan_iter(USER_STATS_ROOT_KEY + ":*"):
        redis.delete(key)


class Linked(NamedTuple):
    apikey: str
    key_id: int


def approved_key(conn: AppDB) -> Linked:
    req = create_user_key_link_request(conn, 1, "nas")
    approve_user_key_link_request(conn, req.link_code, 2)
    return Linked(req.apikey, req.id)


def state(conn: AppDB, apikey: str) -> str | None:
    key = lookup_user_api_key(conn, apikey)
    return None if key is None else key.state


def set_key_values(conn: AppDB, key_id: int, **values: Any) -> None:
    table = schema.account_application_key
    conn.execute(table.update().where(table.c.id == key_id).values(**values))


def last_used(conn: AppDB, key_id: int) -> datetime.date | None:
    table = schema.account_application_key
    query = sql.select(table.c.last_used).where(table.c.id == key_id)
    return conn.execute(query).scalar_one()


def counters(ctx: ScriptContext) -> dict[UserStatsKey, int]:
    result = {}
    for root in ctx.redis.scan_iter(USER_STATS_ROOT_KEY + ":*"):
        for key, count in ctx.redis.hgetall(root).items():
            result[unpack_user_stats_key(key)] = int(count)
    return result


def flush(ctx: ScriptContext) -> None:
    ctx.db.session.commit()
    assert tests.script is not None
    for partition in range(NUM_PARTITIONS):
        run_update_user_stats(tests.script, partition)


def user_stats(ctx: ScriptContext) -> list[tuple[Any, ...]]:
    table = schema.stats_user_lookups
    query = sql.select(
        table.c.date,
        table.c.account_id,
        table.c.application_id,
        table.c.count_hits,
        table.c.count_nohits,
    ).order_by(table.c.account_id)
    return [tuple(row) for row in ctx.db.get_app_db().execute(query)]


def cleanup_db(ctx: ScriptContext) -> None:
    ctx.db.get_app_db().execute(schema.stats_user_lookups.delete())
    ctx.db.get_app_db().execute(schema.account_application_key.delete())
    ctx.db.session.commit()


# Expiry


@with_database
def test_approved_key_lapses_a_year_after_last_use(conn: AppDB) -> None:
    apikey, key_id = approved_key(conn)
    set_key_values(conn, key_id, approved=YEAR_AGO, last_used=TODAY)
    assert lookup_user_api_key(conn, apikey) == UserKey(2, 1, USER_KEY_APPROVED, key_id)
    set_key_values(conn, key_id, last_used=YEAR_AGO)
    assert lookup_user_api_key(conn, apikey) == UserKey(2, 1, USER_KEY_EXPIRED, key_id)


@with_database
def test_never_used_key_lapses_a_year_after_approval(conn: AppDB) -> None:
    key = approved_key(conn)
    set_key_values(conn, key.key_id, approved=YEAR_AGO)
    assert state(conn, key.apikey) == USER_KEY_EXPIRED


@with_database
def test_lapsing_does_not_change_pending_or_revoked_keys(conn: AppDB) -> None:
    pending = create_user_key_link_request(conn, 1, None)
    assert state(conn, pending.apikey) == "pending"
    key = approved_key(conn)
    set_key_values(conn, key.key_id, approved=YEAR_AGO, revoked=sql.func.now())
    assert state(conn, key.apikey) == "revoked"


@with_database
def test_mark_user_key_used_only_moves_forward(conn: AppDB) -> None:
    key = approved_key(conn)
    mark_user_key_used(conn, key.key_id, TODAY)
    mark_user_key_used(conn, key.key_id, TODAY - datetime.timedelta(days=1))
    assert last_used(conn, key.key_id) == TODAY


@with_database
def test_delete_abandoned_link_requests(conn: AppDB) -> None:
    old = create_user_key_link_request(conn, 1, None)
    recent = create_user_key_link_request(conn, 1, None)
    approved = approved_key(conn)
    long_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=31
    )
    table = schema.account_application_key
    conn.execute(
        table.update()
        .where(table.c.apikey.in_([old.apikey, approved.apikey]))
        .values(link_expires=long_ago)
    )
    assert delete_abandoned_link_requests(conn) == 1
    assert lookup_user_api_key(conn, old.apikey) is None
    assert lookup_user_api_key(conn, recent.apikey) is not None
    assert lookup_user_api_key(conn, approved.apikey) is not None


# Counting


def test_user_stats_key_round_trip() -> None:
    packed = pack_user_stats_key(12, 34, 56, "hit")
    assert unpack_user_stats_key(packed) == UserStatsKey(TODAY, 12, 34, 56, "hit")
    packed = pack_user_stats_key(12, 34, None, "submit")
    assert unpack_user_stats_key(packed.encode()) == UserStatsKey(
        TODAY, 12, 34, None, "submit"
    )
    with pytest.raises(ValueError):
        unpack_user_stats_key("2026-01-01:1:2:0:bogus")


@with_script_context
def test_lookups_are_counted_per_user(ctx: ScriptContext) -> None:
    key = approved_key(ctx.db.get_app_db())
    handler = LookupHandler(ctx)
    for user, hit in ((key.apikey, True), ("user1key", False), (None, True)):
        params = LookupHandlerParams(ctx.config)
        values = lookup_values() if user is None else lookup_values(user=user)
        params.parse(values, ctx.db)
        handler._count_lookup(params, hit)
    assert counters(ctx) == {
        UserStatsKey(TODAY, 2, 1, key.key_id, "hit"): 1,
        UserStatsKey(TODAY, 1, 1, None, "miss"): 1,
    }
    cleanup_db(ctx)


@with_script_context
def test_submissions_are_counted_per_user(ctx: ScriptContext) -> None:
    key = approved_key(ctx.db.get_app_db())
    ctx.db.session.commit()
    values = {
        "format": "json",
        "client": "app1key",
        "user": key.apikey,
        "duration": str(TEST_1_LENGTH),
        "fingerprint": TEST_1_FP,
        "mbid": "b9c05616-1874-4d5d-b30e-6b959c922d28",
    }
    resp = SubmitHandler(ctx).handle(
        Request(EnvironBuilder(method="POST", data=values).get_environ())
    )
    assert resp.status_code == 200, resp.data
    assert counters(ctx) == {UserStatsKey(TODAY, 2, 1, key.key_id, "submit"): 1}
    cleanup_db(ctx)


# Flushing


@with_script_context
def test_flush_writes_stats_and_last_used(ctx: ScriptContext) -> None:
    linked = approved_key(ctx.db.get_app_db())
    submitter = approved_key(ctx.db.get_app_db())
    for _ in range(3):
        update_user_counter(ctx.redis, 2, 1, linked.key_id, "hit")
    update_user_counter(ctx.redis, 2, 1, linked.key_id, "miss")
    update_user_counter(ctx.redis, 1, 1, None, "hit")
    # A submission marks its key as used but is not a lookup.
    update_user_counter(ctx.redis, 2, 1, submitter.key_id, "submit")
    try:
        flush(ctx)
        assert user_stats(ctx) == [(TODAY, 1, 1, 1, 0), (TODAY, 2, 1, 3, 1)]
        assert last_used(ctx.db.get_app_db(), linked.key_id) == TODAY
        assert last_used(ctx.db.get_app_db(), submitter.key_id) == TODAY

        # Written counters are cleared, so nothing is counted twice.
        assert set(counters(ctx).values()) == {0}
        flush(ctx)
        assert user_stats(ctx) == [(TODAY, 1, 1, 1, 0), (TODAY, 2, 1, 3, 1)]
        assert counters(ctx) == {}
    finally:
        cleanup_db(ctx)


@with_script_context
def test_flush_discards_what_can_never_be_written(ctx: ScriptContext) -> None:
    root = USER_STATS_ROOT_KEY + ":00"
    ctx.redis.hset(root, "garbage", 1)
    ctx.redis.hset(root, pack_user_stats_key(999999, 1, None, "hit"), 1)
    assert tests.script is not None
    run_update_user_stats(tests.script, 0)
    assert ctx.redis.hgetall(root) == {}


@with_script_context
def test_cleanup_deletes_old_user_stats(ctx: ScriptContext) -> None:
    table = schema.stats_user_lookups
    old = TODAY - const.USER_LOOKUP_STATS_RETENTION - datetime.timedelta(days=1)
    ctx.db.get_app_db().execute(
        table.insert(),
        [
            {"date": old, "account_id": 1, "application_id": 1, "count_hits": 1},
            {"date": TODAY, "account_id": 1, "application_id": 1, "count_hits": 1},
        ],
    )
    ctx.db.session.commit()
    try:
        assert tests.script is not None
        run_cleanup_user_keys(tests.script)
        assert [row[0] for row in user_stats(ctx)] == [TODAY]
    finally:
        cleanup_db(ctx)
