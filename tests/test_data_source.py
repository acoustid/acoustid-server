# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from acoustid.data.source import find_or_insert_source
from tests import with_database


@with_database
def test_find_or_insert_source(conn):
    rows = conn.execute(
        "SELECT id, account_id, application_id FROM source ORDER BY id"
    ).fetchall()
    expected_rows = [
        (1, 1, 1),
        (2, 2, 2),
    ]
    assert expected_rows == rows
    id = find_or_insert_source(conn, 1, 1)
    assert 1 == id
    id = find_or_insert_source(conn, 2, 2)
    assert 2 == id
    id = find_or_insert_source(conn, 1, 2)
    assert 3 == id
    rows = conn.execute(
        "SELECT id, account_id, application_id FROM source ORDER BY id"
    ).fetchall()
    expected_rows = [
        (1, 1, 1),
        (2, 2, 2),
        (3, 2, 1),
    ]
    assert expected_rows == rows
