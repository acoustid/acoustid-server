# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import *
from tests import prepare_database, with_database
from acoustid.data.musicbrainz import find_puid_mbids


@with_database
def test_find_puid_mbids(conn):
    mbids = find_puid_mbids(conn, 'c12f1170-db63-4e85-931b-e46094b49085', 120, 530)
    assert_equals(['8d77b21e-2b41-4751-a88f-a2ab37cbd41c', 'b81f83ee-4da4-11e0-9ed8-0025225356f3'], mbids)
    mbids = find_puid_mbids(conn, 'c12f1170-db63-4e85-931b-e46094b49085', 120, 130)
    assert_equals(['b81f83ee-4da4-11e0-9ed8-0025225356f3'], mbids)
    mbids = find_puid_mbids(conn, 'c12f1170-db63-4e85-931b-e46094b49085', 160, 170)
    assert_equals([], mbids)
    mbids = find_puid_mbids(conn, 'c12f1170-db63-4e85-931b-e46094123456', 120, 130)
    assert_equals([], mbids)

