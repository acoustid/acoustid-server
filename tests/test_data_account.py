# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import assert_equals, assert_not_equal, assert_true
from tests import with_database
from acoustid.data.account import (
    lookup_account_id_by_apikey,
    get_account_details,
    reset_account_apikey,
    update_account_lastlogin,
)


@with_database
def test_lookup_account_id_by_apikey(conn):
    id = lookup_account_id_by_apikey(conn, 'user1key')
    assert_equals(1, id)
    id = lookup_account_id_by_apikey(conn, 'foooo')
    assert_equals(None, id)


@with_database
def test_reset_account_apikey(conn):
    info = get_account_details(conn, 1)
    assert_equals('user1key', info['apikey'])
    reset_account_apikey(conn, 1)
    info = get_account_details(conn, 1)
    assert_not_equal('user1key', info['apikey'])


@with_database
def test_update_account_lastlogin(conn):
    info1 = get_account_details(conn, 1)
    update_account_lastlogin(conn, 1)
    info2 = get_account_details(conn, 1)
    assert_true(info1['lastlogin'] < info2['lastlogin'])
