# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import *
from tests import prepare_database, with_database
from acoustid.data.account import (
    lookup_account_id_by_apikey,
    get_account_details,
    reset_account_apikey,
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
    assert_equal('user1key', info['apikey'])
    reset_account_apikey(conn, 1)
    info = get_account_details(conn, 1)
    assert_not_equal('user1key', info['apikey'])

