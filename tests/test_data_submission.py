# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import *
from tests import prepare_database, with_database
from acoustid.data.submission import insert_submission


@with_database
def test_insert_submission(conn):
    id = insert_submission(conn, {
        'fingerprint': [1,2,3,4,5,6],
        'length': 123,
        'bitrate': 192,
        'source_id': 1,
        'format_id': 1,
    })
    assert_equals(1, id)
    rows = conn.execute("""
        SELECT fingerprint, length, bitrate, source_id, format_id
        FROM submission WHERE id=%s
    """, (id,)).fetchall()
    expected_rows = [
        ([1,2,3,4,5,6], 123, 192, 1, 1),
    ]
    assert_equals(expected_rows, rows)

