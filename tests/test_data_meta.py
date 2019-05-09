# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import assert_equals
from tests import with_database
from acoustid.data.meta import insert_meta


@with_database
def test_insert_meta(conn):
    id = insert_meta(conn, {
        'track': 'Voodoo People',
        'artist': 'The Prodigy',
        'album': 'Music For The Jitled People',
        'album_artist': 'Prodigy',
        'track_no': 2,
        'disc_no': 3,
        'year': 2030
    })
    assert_equals(3, id)
    row = conn.execute("SELECT * FROM meta WHERE id=%s", id).fetchone()
    expected = {
        'id': id,
        'track': 'Voodoo People',
        'artist': 'The Prodigy',
        'album': 'Music For The Jitled People',
        'album_artist': 'Prodigy',
        'track_no': 2,
        'disc_no': 3,
        'year': 2030
    }
    assert_equals(expected, dict(row))
