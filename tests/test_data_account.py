# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from typing import Iterator
from unittest import mock

import pytest
from redis import Redis
from sqlalchemy import sql

import tests
from acoustid.data import account as account_data
from acoustid.data.account import (
    USER_KEY_APPROVED,
    USER_KEY_CACHE_PREFIX,
    USER_KEY_DECLINED,
    USER_KEY_EXPIRED,
    USER_KEY_PENDING,
    USER_KEY_REVOKED,
    UserKey,
    approve_user_key_link_request,
    cache_user_key,
    create_user_key_link_request,
    decline_user_key_link_request,
    format_link_code,
    get_account_details,
    lookup_account_id_by_apikey,
    lookup_user_api_key,
    normalize_link_code,
    read_cached_user_key,
    refresh_cached_user_key,
    reset_account_apikey,
    revoke_user_application_key,
    update_account_lastlogin,
)
from acoustid.db import AppDB
from tests import with_database


@with_database
def test_lookup_account_id_by_apikey(conn):
    id = lookup_account_id_by_apikey(conn, "user1key")
    assert id == 1
    id = lookup_account_id_by_apikey(conn, "foooo")
    assert id is None


@with_database
def test_reset_account_apikey(conn):
    info = get_account_details(conn, 1)
    assert info is not None
    assert info["apikey"] == "user1key"
    reset_account_apikey(conn, 1)
    info = get_account_details(conn, 1)
    assert info is not None
    assert info["apikey"] != "user1key"


@with_database
def test_update_account_lastlogin(conn):
    info1 = get_account_details(conn, 1)
    assert info1 is not None
    update_account_lastlogin(conn, 1)
    info2 = get_account_details(conn, 1)
    assert info2 is not None
    assert info1["lastlogin"] < info2["lastlogin"]


def expire_link_requests(conn: AppDB) -> None:
    conn.execute(
        sql.text(
            "UPDATE account_application_key SET link_expires = now() - interval '1 second'"
        )
    )


@with_database
def test_lookup_user_api_key_account_key(conn: AppDB) -> None:
    assert lookup_user_api_key(conn, "user1key") == UserKey(1, None, USER_KEY_APPROVED)
    assert lookup_user_api_key(conn, "foooo") is None


@with_database
def test_link_request_lifecycle(conn: AppDB) -> None:
    req = create_user_key_link_request(conn, 1, "nas")
    assert lookup_user_api_key(conn, req.apikey) == UserKey(
        None, 1, USER_KEY_PENDING, req.id
    )

    code = format_link_code(req.link_code).lower()
    assert approve_user_key_link_request(conn, code, 2) == req.apikey
    assert lookup_user_api_key(conn, req.apikey) == UserKey(
        2, 1, USER_KEY_APPROVED, req.id
    )

    # The code is consumed, so it cannot bind the key a second time.
    assert approve_user_key_link_request(conn, req.link_code, 1) is None
    assert decline_user_key_link_request(conn, req.link_code) is None

    assert revoke_user_application_key(conn, req.id, 1) is None
    assert revoke_user_application_key(conn, req.id, 2) == req.apikey
    assert revoke_user_application_key(conn, req.id, 2) is None
    assert lookup_user_api_key(conn, req.apikey) == UserKey(
        2, 1, USER_KEY_REVOKED, req.id
    )


@with_database
def test_declined_link_request(conn: AppDB) -> None:
    req = create_user_key_link_request(conn, 1, None)
    assert decline_user_key_link_request(conn, req.link_code) == req.apikey
    assert approve_user_key_link_request(conn, req.link_code, 1) is None
    assert lookup_user_api_key(conn, req.apikey) == UserKey(
        None, 1, USER_KEY_DECLINED, req.id
    )


@with_database
def test_expired_link_request(conn: AppDB) -> None:
    req = create_user_key_link_request(conn, 1, None)
    expire_link_requests(conn)
    assert approve_user_key_link_request(conn, req.link_code, 1) is None
    assert decline_user_key_link_request(conn, req.link_code) is None
    assert lookup_user_api_key(conn, req.apikey) == UserKey(
        None, 1, USER_KEY_EXPIRED, req.id
    )


@with_database
def test_approved_key_does_not_expire_with_its_link(conn: AppDB) -> None:
    req = create_user_key_link_request(conn, 1, None)
    approve_user_key_link_request(conn, req.link_code, 1)
    expire_link_requests(conn)
    assert lookup_user_api_key(conn, req.apikey) == UserKey(
        1, 1, USER_KEY_APPROVED, req.id
    )


@with_database
def test_link_request_never_reuses_an_account_key(conn: AppDB) -> None:
    keys = iter(["user1key", "fresh-key"])
    with mock.patch.object(account_data, "generate_api_key", lambda: next(keys)):
        req = create_user_key_link_request(conn, 1, None)
    assert req.apikey == "fresh-key"


def test_normalize_link_code() -> None:
    assert normalize_link_code(" 4kmq-7t2x ") == "4KMQ7T2X"
    assert normalize_link_code("o1li") == "0111"


@pytest.fixture
def redis() -> Iterator[Redis]:
    assert tests.script is not None
    client = tests.script.get_redis()
    yield client
    for key in client.scan_iter(USER_KEY_CACHE_PREFIX + "test-*"):
        client.delete(key)


def test_user_key_cache_round_trip(redis: Redis) -> None:
    assert read_cached_user_key(redis, "test-missing") == (False, None)

    cache_user_key(redis, "test-unknown", None)
    assert read_cached_user_key(redis, "test-unknown") == (True, None)
    assert redis.ttl(USER_KEY_CACHE_PREFIX + "test-unknown") <= 5

    key = UserKey(1, 2, USER_KEY_APPROVED)
    cache_user_key(redis, "test-key", key)
    assert read_cached_user_key(redis, "test-key") == (True, key)


def test_user_key_cache_fill_does_not_overwrite(redis: Redis) -> None:
    """A stale read from a replica must not undo a change just published."""
    revoked = UserKey(1, 2, USER_KEY_REVOKED)
    cache_user_key(redis, "test-key", revoked, replace=True)
    cache_user_key(redis, "test-key", UserKey(1, 2, USER_KEY_APPROVED))
    assert read_cached_user_key(redis, "test-key") == (True, revoked)


@with_database
def test_refresh_cached_user_key_after_approval(conn: AppDB) -> None:
    assert tests.script is not None
    redis = tests.script.get_redis()
    req = create_user_key_link_request(conn, 1, None)
    try:
        cache_user_key(redis, req.apikey, lookup_user_api_key(conn, req.apikey))
        approve_user_key_link_request(conn, req.link_code, 2)
        refresh_cached_user_key(redis, conn, req.apikey)
        assert read_cached_user_key(redis, req.apikey) == (
            True,
            UserKey(2, 1, USER_KEY_APPROVED, req.id),
        )
    finally:
        redis.delete(USER_KEY_CACHE_PREFIX + req.apikey)


def test_undecodable_cached_user_key_is_a_miss(redis: Redis) -> None:
    """An entry from a version with a different UserKey must not fail lookups."""
    redis.set(USER_KEY_CACHE_PREFIX + "test-old", "[1, 2]")
    redis.set(USER_KEY_CACHE_PREFIX + "test-junk", "{")
    assert read_cached_user_key(redis, "test-old") == (False, None)
    assert read_cached_user_key(redis, "test-junk") == (False, None)
