# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from sqlalchemy import sql

from acoustid.data.format import find_or_insert_format
from tests import with_database


@with_database
def test_find_or_insert_format(conn):
    id = find_or_insert_format(conn, "FLAC")
    assert 1 == id
    id = find_or_insert_format(conn, "MP3")
    assert 2 == id
    rows = conn.execute(sql.text("SELECT id, name FROM format ORDER BY id")).all()
    expected_rows = [
        (1, "FLAC"),
        (2, "MP3"),
    ]
    assert expected_rows == rows
