# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from tests import with_database
from acoustid.data.format import find_or_insert_format


@with_database
def test_find_or_insert_format(conn):
    id = find_or_insert_format(conn, 'FLAC')
    assert 1 == id
    id = find_or_insert_format(conn, 'MP3')
    assert 2 == id
    rows = conn.execute("SELECT id, name FROM format ORDER BY id").fetchall()
    expected_rows = [
        (1, 'FLAC'),
        (2, 'MP3'),
    ]
    assert expected_rows == rows
