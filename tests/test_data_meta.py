# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import assert_equals
from tests import with_script_context
from acoustid.script import ScriptContext
from acoustid.data.meta import insert_meta


@with_script_context
def test_insert_meta(ctx):
    # type: (ScriptContext) -> None
    meta_id = insert_meta(ctx.db.get_fingerprint_db(), {
        'track': 'Voodoo People',
        'artist': 'The Prodigy',
        'album': 'Music For The Jitled People',
        'album_artist': 'Prodigy',
        'track_no': 2,
        'disc_no': 3,
        'year': 2030
    })
    assert_equals(3, meta_id)
    row = ctx.db.get_fingerprint_db().execute("SELECT * FROM meta WHERE id=%s", meta_id).fetchone()
    expected = {
        'id': meta_id,
        'track': 'Voodoo People',
        'artist': 'The Prodigy',
        'album': 'Music For The Jitled People',
        'album_artist': 'Prodigy',
        'track_no': 2,
        'disc_no': 3,
        'year': 2030
    }
    assert_equals(expected, dict(row))
