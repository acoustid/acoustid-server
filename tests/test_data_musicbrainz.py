# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import uuid

from sqlalchemy import sql

from acoustid import tables as schema
from acoustid.api import serialize_response
from acoustid.api.v2 import LookupHandler
from acoustid.data.musicbrainz import _load_isrcs, lookup_metadata
from acoustid.script import ScriptContext
from tests import with_script_context

RECORDING_1 = "77ef7468-e8f8-4b3e-93c5-a5a8b0a6ec4a"
RECORDING_2 = "5b1e1b26-a3b8-4ba0-8d21-c1f0f9e8fdf6"


def insert_recording(conn, gid, name, artist_credit):
    result = conn.execute(
        schema.mb_recording.insert().values(
            gid=uuid.UUID(gid), name=name, artist_credit=artist_credit, length=180000
        )
    )
    return result.inserted_primary_key[0]


def insert_artist_credit(conn, name="Various Artists"):
    """A credit plus the artist behind it.

    lookup_metadata resolves artists for every row and raises if a credit has no
    artist_credit_name, so a bare credit row is not enough to stand a recording
    up.
    """
    result = conn.execute(
        schema.mb_artist_credit.insert().values(name=name, artist_count=1, ref_count=1)
    )
    artist_credit_id = result.inserted_primary_key[0]

    result = conn.execute(
        schema.mb_artist.insert().values(gid=uuid.uuid4(), name=name, sort_name=name)
    )
    artist_id = result.inserted_primary_key[0]

    conn.execute(
        schema.mb_artist_credit_name.insert().values(
            artist_credit=artist_credit_id,
            position=0,
            artist=artist_id,
            name=name,
            join_phrase="",
        )
    )
    return artist_credit_id


def insert_isrc(conn, recording_id, isrc):
    conn.execute(
        schema.mb_isrc.insert().values(recording=recording_id, isrc=isrc, source=0)
    )


@with_script_context
def test_load_isrcs_groups_by_recording(ctx: ScriptContext) -> None:
    conn = ctx.db.get_musicbrainz_db()
    ac = insert_artist_credit(conn)
    id1 = insert_recording(conn, RECORDING_1, "Track One", ac)
    id2 = insert_recording(conn, RECORDING_2, "Track Two", ac)
    insert_isrc(conn, id1, "GBAYE0601498")
    insert_isrc(conn, id2, "USRC17607839")

    isrcs = _load_isrcs(conn, [RECORDING_1, RECORDING_2])

    assert isrcs == {
        RECORDING_1: ["GBAYE0601498"],
        RECORDING_2: ["USRC17607839"],
    }


@with_script_context
def test_load_isrcs_returns_every_code_for_one_recording(ctx: ScriptContext) -> None:
    """A recording can carry several. Returning only one would be arbitrary."""
    conn = ctx.db.get_musicbrainz_db()
    ac = insert_artist_credit(conn)
    id1 = insert_recording(conn, RECORDING_1, "Track One", ac)
    insert_isrc(conn, id1, "USRC17607839")
    insert_isrc(conn, id1, "GBAYE0601498")

    isrcs = _load_isrcs(conn, [RECORDING_1])

    # Sorted, so identical requests do not reorder between calls.
    assert isrcs == {RECORDING_1: ["GBAYE0601498", "USRC17607839"]}


@with_script_context
def test_load_isrcs_omits_recordings_without_any(ctx: ScriptContext) -> None:
    conn = ctx.db.get_musicbrainz_db()
    ac = insert_artist_credit(conn)
    insert_recording(conn, RECORDING_1, "Track One", ac)

    assert _load_isrcs(conn, [RECORDING_1]) == {}


@with_script_context
def test_load_isrcs_with_no_recordings_does_not_query(ctx: ScriptContext) -> None:
    conn = ctx.db.get_musicbrainz_db()
    assert _load_isrcs(conn, []) == {}


@with_script_context
def test_lookup_metadata_attaches_isrcs_when_asked(ctx: ScriptContext) -> None:
    conn = ctx.db.get_musicbrainz_db()
    ac = insert_artist_credit(conn)
    id1 = insert_recording(conn, RECORDING_1, "Track One", ac)
    insert_isrc(conn, id1, "GBAYE0601498")

    results = lookup_metadata(conn, [RECORDING_1], load_isrcs=True)

    assert len(results) == 1
    assert results[0]["recording_isrcs"] == ["GBAYE0601498"]


@with_script_context
def test_lookup_metadata_leaves_isrcs_out_by_default(ctx: ScriptContext) -> None:
    """Costs an extra query, so nobody pays for it who did not ask."""
    conn = ctx.db.get_musicbrainz_db()
    ac = insert_artist_credit(conn)
    id1 = insert_recording(conn, RECORDING_1, "Track One", ac)
    insert_isrc(conn, id1, "GBAYE0601498")

    results = lookup_metadata(conn, [RECORDING_1])

    assert "recording_isrcs" not in results[0]


@with_script_context
def test_lookup_metadata_gives_an_empty_list_for_a_recording_with_none(
    ctx: ScriptContext,
) -> None:
    conn = ctx.db.get_musicbrainz_db()
    ac = insert_artist_credit(conn)
    insert_recording(conn, RECORDING_1, "Track One", ac)

    results = lookup_metadata(conn, [RECORDING_1], load_isrcs=True)

    assert results[0]["recording_isrcs"] == []


@with_script_context
def test_isrcs_do_not_multiply_release_rows(ctx: ScriptContext) -> None:
    """The reason this is a second query rather than a join.

    A recording with two ISRCs joined into the main query would return two rows
    per release, and the caller groups by recording, so every release under it
    would appear twice.
    """
    conn = ctx.db.get_musicbrainz_db()
    ac = insert_artist_credit(conn)
    id1 = insert_recording(conn, RECORDING_1, "Track One", ac)
    insert_isrc(conn, id1, "USRC17607839")
    insert_isrc(conn, id1, "GBAYE0601498")

    without = lookup_metadata(conn, [RECORDING_1])
    with_isrcs = lookup_metadata(conn, [RECORDING_1], load_isrcs=True)

    assert len(with_isrcs) == len(without) == 1


@with_script_context
def test_extract_recording_emits_isrcs(ctx: ScriptContext) -> None:
    handler = LookupHandler(ctx)
    recording = handler.extract_recording(
        {
            "recording_id": RECORDING_1,
            "recording_title": "Track One",
            "recording_duration": 180,
            "recording_artists": [],
            "recording_isrcs": ["GBAYE0601498", "USRC17607839"],
        }
    )
    assert recording["isrcs"] == ["GBAYE0601498", "USRC17607839"]


@with_script_context
def test_extract_recording_omits_isrcs_when_there_are_none(ctx: ScriptContext) -> None:
    """Absent rather than an empty list, so a caller that did not ask sees no
    change and one that did is not handed a field meaning nothing."""
    handler = LookupHandler(ctx)
    recording = handler.extract_recording(
        {
            "recording_id": RECORDING_1,
            "recording_title": "Track One",
            "recording_duration": 180,
            "recording_artists": [],
            "recording_isrcs": [],
        }
    )
    assert "isrcs" not in recording

    # And when the field was never loaded at all.
    recording = handler.extract_recording(
        {
            "recording_id": RECORDING_1,
            "recording_title": "Track One",
            "recording_duration": 180,
            "recording_artists": [],
        }
    )
    assert "isrcs" not in recording


def test_isrcs_serialize_as_a_list_in_xml() -> None:
    """singular("isrcs") is "isrc", so the generic list writer already does the
    right thing and no serialiser change is needed."""
    resp = serialize_response(
        {"status": "ok", "isrcs": ["GBAYE0601498", "USRC17607839"]}, "xml"
    )
    assert b"<isrcs><isrc>GBAYE0601498</isrc><isrc>USRC17607839</isrc></isrcs>" in (
        resp.data
    )


@with_script_context
def test_isrc_table_is_reachable(ctx: ScriptContext) -> None:
    """Guards the assumption the whole feature rests on: that the mirror this
    server reads actually carries musicbrainz.isrc."""
    conn = ctx.db.get_musicbrainz_db()
    conn.execute(sql.select(sql.func.count()).select_from(schema.mb_isrc))
