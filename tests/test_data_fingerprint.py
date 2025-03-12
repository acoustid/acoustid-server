# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from sqlalchemy import sql

from acoustid.data.fingerprint import insert_fingerprint
from acoustid.script import ScriptContext
from tests import with_script_context


@with_script_context
def test_insert_fingerprint(ctx):
    # type: (ScriptContext) -> None
    fingerprint_db = ctx.db.get_fingerprint_db()
    ingest_db = ctx.db.get_ingest_db()
    fingerprint_id = insert_fingerprint(
        fingerprint_db,
        ingest_db,
        {
            "fingerprint": [1, 2, 3, 4, 5, 6],
            "length": 123,
            "bitrate": 192,
            "source_id": 1,
            "format_id": 1,
            "track_id": 2,
        },
    )
    assert 1 == fingerprint_id
    result = fingerprint_db.execute(
        sql.text(
            """
        SELECT fingerprint, length, bitrate, format_id, track_id
        FROM fingerprint WHERE id=:id
        """
        ),
        {"id": fingerprint_id},
    )
    rows = result.fetchall()
    expected_rows = [
        ([1, 2, 3, 4, 5, 6], 123, 192, 1, 2),
    ]
    assert expected_rows == rows
