# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import uuid

from sqlalchemy import sql

from acoustid.data.meta import generate_meta_gid, insert_meta
from acoustid.script import ScriptContext
from tests import with_script_context


def test_generate_meta_gid() -> None:
    assert uuid.UUID("781f130c-a3b4-5090-a87a-816c30bed2a5") == generate_meta_gid({})
    assert uuid.UUID("781f130c-a3b4-5090-a87a-816c30bed2a5") == generate_meta_gid(
        {"track": ""}
    )
    assert uuid.UUID("454238f5-bceb-53c9-8a2c-029e79b86e26") == generate_meta_gid(
        {"track": "foo"}
    )
    assert uuid.UUID("9c29eeb7-47d9-5364-935a-6a36b0f3bca0") == generate_meta_gid(
        {"track": "luk\xe1\u0161"}
    )
    assert uuid.UUID("9acff514-86bf-5fcd-9253-03b8e91bc9ae") == generate_meta_gid(
        {"track": "foo", "year": 1}
    )


@with_script_context
def test_insert_meta(ctx: ScriptContext) -> None:
    meta_id, meta_gid = insert_meta(
        ctx.db.get_fingerprint_db(),
        {
            "track": "Voodoo People",
            "artist": "The Prodigy",
            "album": "Music For The Jitled People",
            "album_artist": "Prodigy",
            "track_no": 2,
            "disc_no": 3,
            "year": 2030,
        },
    )
    assert 3 == meta_id
    assert uuid.UUID("398d828b-b601-5c58-a135-d5c81116da7c") == meta_gid
    row = dict(
        ctx.db.get_fingerprint_db()
        .execute(sql.text("SELECT * FROM meta WHERE id=:id"), {"id": meta_id})
        .one()
        ._mapping
    )
    expected = {
        "id": meta_id,
        "track": "Voodoo People",
        "artist": "The Prodigy",
        "album": "Music For The Jitled People",
        "album_artist": "Prodigy",
        "track_no": 2,
        "disc_no": 3,
        "year": 2030,
        "gid": uuid.UUID("398d828b-b601-5c58-a135-d5c81116da7c"),
    }
    assert row["created"] is not None
    del row["created"]
    assert expected == row
