# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from unittest import mock

from sqlalchemy import sql

from acoustid.data import account as account_data
from acoustid.data.account import (
    USER_KEY_APPROVED,
    USER_KEY_DECLINED,
    USER_KEY_EXPIRED,
    USER_KEY_PENDING,
    USER_KEY_REVOKED,
    UserKey,
    approve_user_key_link_request,
    create_user_key_link_request,
    decline_user_key_link_request,
    format_link_code,
    get_account_details,
    lookup_account_id_by_apikey,
    lookup_user_api_key,
    normalize_link_code,
    reset_account_apikey,
    revoke_user_application_key,
    update_account_lastlogin,
)
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


def expire_link_requests(conn):
    conn.execute(
        sql.text(
            "UPDATE account_application_key SET link_expires = now() - interval '1 second'"
        )
    )


@with_database
def test_lookup_user_api_key_account_key(conn):
    assert lookup_user_api_key(conn, "user1key") == UserKey(1, None, USER_KEY_APPROVED)
    assert lookup_user_api_key(conn, "foooo") is None


@with_database
def test_link_request_lifecycle(conn):
    req = create_user_key_link_request(conn, 1, "nas")
    assert lookup_user_api_key(conn, req.apikey) == UserKey(None, 1, USER_KEY_PENDING)

    code = format_link_code(req.link_code).lower()
    assert approve_user_key_link_request(conn, code, 2) == req.id
    assert lookup_user_api_key(conn, req.apikey) == UserKey(2, 1, USER_KEY_APPROVED)

    # The code is consumed, so it cannot bind the key a second time.
    assert approve_user_key_link_request(conn, req.link_code, 1) is None
    assert decline_user_key_link_request(conn, req.link_code) is None

    assert not revoke_user_application_key(conn, req.id, 1)
    assert revoke_user_application_key(conn, req.id, 2)
    assert not revoke_user_application_key(conn, req.id, 2)
    assert lookup_user_api_key(conn, req.apikey) == UserKey(2, 1, USER_KEY_REVOKED)


@with_database
def test_declined_link_request(conn):
    req = create_user_key_link_request(conn, 1, None)
    assert decline_user_key_link_request(conn, req.link_code) == req.id
    assert approve_user_key_link_request(conn, req.link_code, 1) is None
    assert lookup_user_api_key(conn, req.apikey) == UserKey(None, 1, USER_KEY_DECLINED)


@with_database
def test_expired_link_request(conn):
    req = create_user_key_link_request(conn, 1, None)
    expire_link_requests(conn)
    assert approve_user_key_link_request(conn, req.link_code, 1) is None
    assert decline_user_key_link_request(conn, req.link_code) is None
    assert lookup_user_api_key(conn, req.apikey) == UserKey(None, 1, USER_KEY_EXPIRED)


@with_database
def test_approved_key_does_not_expire_with_its_link(conn):
    req = create_user_key_link_request(conn, 1, None)
    approve_user_key_link_request(conn, req.link_code, 1)
    expire_link_requests(conn)
    assert lookup_user_api_key(conn, req.apikey) == UserKey(1, 1, USER_KEY_APPROVED)


@with_database
def test_link_request_never_reuses_an_account_key(conn):
    keys = iter(["user1key", "fresh-key"])
    with mock.patch.object(account_data, "generate_api_key", lambda: next(keys)):
        req = create_user_key_link_request(conn, 1, None)
    assert req.apikey == "fresh-key"


def test_normalize_link_code():
    assert normalize_link_code(" 4kmq-7t2x ") == "4KMQ7T2X"
    assert normalize_link_code("o1li") == "0111"
