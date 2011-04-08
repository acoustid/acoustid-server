# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

from nose.tools import *
from tests import prepare_database, with_database
from acoustid.data.application import lookup_application_id_by_apikey


@with_database
def test_lookup_application_id_by_apikey(conn):
    prepare_database(conn, """
INSERT INTO account (name, apikey) VALUES ('User', 'userkey');
INSERT INTO application (name, apikey, version, account_id) VALUES ('App', 'appkey', '0.1', 1);
""")
    id = lookup_application_id_by_apikey(conn, 'appkey')
    assert_equals(1, id)
    id = lookup_application_id_by_apikey(conn, 'foooo')
    assert_equals(None, id)

