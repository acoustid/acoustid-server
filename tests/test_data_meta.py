# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import uuid
from nose.tools import assert_equals
from tests import with_script_context
from acoustid.script import ScriptContext
from acoustid.data.meta import insert_meta, generate_meta_gid


def test_generate_meta_gid():
    assert_equals(uuid.UUID('781f130c-a3b4-5090-a87a-816c30bed2a5'), generate_meta_gid({}))
    assert_equals(uuid.UUID('781f130c-a3b4-5090-a87a-816c30bed2a5'), generate_meta_gid({'track': u''}))
    assert_equals(uuid.UUID('454238f5-bceb-53c9-8a2c-029e79b86e26'), generate_meta_gid({'track': u'foo'}))
    assert_equals(uuid.UUID('9c29eeb7-47d9-5364-935a-6a36b0f3bca0'), generate_meta_gid({'track': u'luk\xe1\u0161'}))
    assert_equals(uuid.UUID('9acff514-86bf-5fcd-9253-03b8e91bc9ae'), generate_meta_gid({'track': u'foo', 'year': 1}))


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
    row = dict(ctx.db.get_fingerprint_db().execute("SELECT * FROM meta WHERE id=%s", meta_id).fetchone())
    expected = {
        'id': meta_id,
        'track': 'Voodoo People',
        'artist': 'The Prodigy',
        'album': 'Music For The Jitled People',
        'album_artist': 'Prodigy',
        'track_no': 2,
        'disc_no': 3,
        'year': 2030,
        'gid': uuid.UUID('398d828b-b601-5c58-a135-d5c81116da7c'),
    }
    assert row['created'] is not None
    del row['created']
    assert_equals(expected, row)
