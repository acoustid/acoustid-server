# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import assert_equals
from tests import with_database
from acoustid.data.fingerprint import insert_fingerprint


@with_database
def test_insert_fingerprint(conn):
    id = insert_fingerprint(conn, {
        'fingerprint': [1, 2, 3, 4, 5, 6],
        'length': 123,
        'bitrate': 192,
        'source_id': 1,
        'format_id': 1,
        'track_id': 2,
    })
    assert_equals(1, id)
    rows = conn.execute("""
        SELECT fingerprint, length, bitrate, format_id, track_id
        FROM fingerprint WHERE id=%s
    """, (id,)).fetchall()
    expected_rows = [
        ([1, 2, 3, 4, 5, 6], 123, 192, 1, 2),
    ]
    assert_equals(expected_rows, rows)
