# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from tests import with_database
from acoustid.data.application import lookup_application_id_by_apikey


@with_database
def test_lookup_application_id_by_apikey(conn):
    id = lookup_application_id_by_apikey(conn, 'app1key')
    assert 1 == id
    id = lookup_application_id_by_apikey(conn, 'foooo')
    assert id is None
