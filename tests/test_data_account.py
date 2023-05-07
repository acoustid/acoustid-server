# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from acoustid.data.account import (
    get_account_details,
    lookup_account_id_by_apikey,
    reset_account_apikey,
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
    assert info["apikey"] == "user1key"
    reset_account_apikey(conn, 1)
    info = get_account_details(conn, 1)
    assert info["apikey"] != "user1key"


@with_database
def test_update_account_lastlogin(conn):
    info1 = get_account_details(conn, 1)
    update_account_lastlogin(conn, 1)
    info2 = get_account_details(conn, 1)
    assert info1["lastlogin"] < info2["lastlogin"]
