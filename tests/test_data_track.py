# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from uuid import UUID

from acoustid.data.submission import insert_submission
from acoustid.data.track import (
    can_add_fp_to_track,
    can_merge_tracks,
    insert_track,
    merge_mbids,
    merge_missing_mbid,
    merge_tracks,
)
from acoustid.script import ScriptContext
from tests import (
    TEST_1A_FP_RAW,
    TEST_1A_LENGTH,
    TEST_1B_FP_RAW,
    TEST_1B_LENGTH,
    TEST_2_FP_RAW,
    TEST_2_LENGTH,
    prepare_database,
    with_script_context,
)


@with_script_context
def test_merge_mbids(ctx):
    # type: (ScriptContext) -> None
    insert_submission(
        ctx.db.get_ingest_db(), {"fingerprint": [1], "length": 123, "source_id": 1}
    )
    insert_submission(
        ctx.db.get_ingest_db(), {"fingerprint": [1], "length": 123, "source_id": 1}
    )
    prepare_database(
        ctx.db.get_fingerprint_db(),
        """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (id, track_id, mbid, submission_count) VALUES (1, 1, '97edb73c-4dac-11e0-9096-0025225356f3', 9);
INSERT INTO track_mbid (id, track_id, mbid, submission_count) VALUES (2, 1, 'd575d506-4da4-11e0-b951-0025225356f3', 11);
""",
    )
    prepare_database(
        ctx.db.get_ingest_db(),
        """
INSERT INTO track_mbid_source (track_mbid_id, submission_id, source_id) VALUES (1, 1, 1);
INSERT INTO track_mbid_source (track_mbid_id, submission_id, source_id) VALUES (2, 2, 1);
INSERT INTO track_mbid_change (track_mbid_id, account_id, disabled) VALUES (1, 1, true);
INSERT INTO track_mbid_change (track_mbid_id, account_id, disabled) VALUES (2, 1, true);
""",
    )

    merge_mbids(
        ctx.db.get_fingerprint_db(),
        ctx.db.get_ingest_db(),
        "97edb73c-4dac-11e0-9096-0025225356f3",
        ["d575d506-4da4-11e0-b951-0025225356f3"],
    )

    rows = (
        ctx.db.get_fingerprint_db()
        .execute(
            "SELECT track_id, mbid, submission_count, disabled FROM track_mbid ORDER BY track_id, mbid"
        )
        .fetchall()
    )
    expected_rows = [
        (1, UUID("97edb73c-4dac-11e0-9096-0025225356f3"), 20, False),
    ]
    assert expected_rows == rows

    query = "SELECT track_mbid_id, submission_id, source_id FROM track_mbid_source ORDER BY track_mbid_id, submission_id, source_id"
    rows = ctx.db.get_fingerprint_db().execute(query).fetchall()
    expected_rows2 = [
        (1, 1, 1),
        (1, 2, 1),
    ]
    assert expected_rows2 == rows

    rows = (
        ctx.db.get_fingerprint_db()
        .execute(
            "SELECT track_mbid_id, account_id FROM track_mbid_change ORDER BY track_mbid_id, account_id"
        )
        .fetchall()
    )
    expected_rows3 = [
        (1, 1),
        (1, 1),
    ]
    assert expected_rows3 == rows


@with_script_context
def test_merge_mbids_disabled_target(ctx):
    # type: (ScriptContext) -> None
    prepare_database(
        ctx.db.get_fingerprint_db(),
        """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f3', 9, true);
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (1, 'd575d506-4da4-11e0-b951-0025225356f3', 11);
""",
    )

    merge_mbids(
        ctx.db.get_fingerprint_db(),
        ctx.db.get_ingest_db(),
        "97edb73c-4dac-11e0-9096-0025225356f3",
        ["d575d506-4da4-11e0-b951-0025225356f3"],
    )

    rows = (
        ctx.db.get_fingerprint_db()
        .execute(
            "SELECT track_id, mbid, submission_count, disabled FROM track_mbid ORDER BY track_id, mbid"
        )
        .fetchall()
    )
    expected_rows = [
        (1, UUID("97edb73c-4dac-11e0-9096-0025225356f3"), 20, False),
    ]
    assert expected_rows == rows


@with_script_context
def test_merge_mbids_disabled_source(ctx):
    # type: (ScriptContext) -> None
    prepare_database(
        ctx.db.get_fingerprint_db(),
        """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f3', 9);
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (1, 'd575d506-4da4-11e0-b951-0025225356f3', 11, true);
""",
    )
    merge_mbids(
        ctx.db.get_fingerprint_db(),
        ctx.db.get_ingest_db(),
        "97edb73c-4dac-11e0-9096-0025225356f3",
        ["d575d506-4da4-11e0-b951-0025225356f3"],
    )
    rows = (
        ctx.db.get_fingerprint_db()
        .execute(
            "SELECT track_id, mbid, submission_count, disabled FROM track_mbid ORDER BY track_id, mbid"
        )
        .fetchall()
    )
    expected_rows = [
        (1, UUID("97edb73c-4dac-11e0-9096-0025225356f3"), 20, False),
    ]
    assert expected_rows == rows


@with_script_context
def test_merge_mbids_disabled_both(ctx):
    # type: (ScriptContext) -> None
    prepare_database(
        ctx.db.get_fingerprint_db(),
        """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f3', 9, true);
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (1, 'd575d506-4da4-11e0-b951-0025225356f3', 11, true);
""",
    )
    merge_mbids(
        ctx.db.get_fingerprint_db(),
        ctx.db.get_ingest_db(),
        "97edb73c-4dac-11e0-9096-0025225356f3",
        ["d575d506-4da4-11e0-b951-0025225356f3"],
    )
    rows = (
        ctx.db.get_fingerprint_db()
        .execute(
            "SELECT track_id, mbid, submission_count, disabled FROM track_mbid ORDER BY track_id, mbid"
        )
        .fetchall()
    )
    expected_rows = [
        (1, UUID("97edb73c-4dac-11e0-9096-0025225356f3"), 20, True),
    ]
    assert expected_rows == rows


@with_script_context
def test_merge_missing_mbid(ctx: ScriptContext) -> None:
    from mbdata.sample_data import create_sample_data
    from sqlalchemy.orm import Session

    create_sample_data(Session(ctx.db.get_fingerprint_db()))
    prepare_database(
        ctx.db.get_fingerprint_db(),
        """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f3', 1);
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (1, 'b81f83ee-4da4-11e0-9ed8-0025225356f3', 1);
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (1, 'd575d506-4da4-11e0-b951-0025225356f3', 1);
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (2, 'd575d506-4da4-11e0-b951-0025225356f3', 1);
INSERT INTO musicbrainz.recording_gid_redirect (new_id, gid) VALUES
    (7134047, 'd575d506-4da4-11e0-b951-0025225356f3');
""",
    )
    merge_missing_mbid(
        fingerprint_db=ctx.db.get_fingerprint_db(),
        ingest_db=ctx.db.get_ingest_db(),
        musicbrainz_db=ctx.db.get_musicbrainz_db(),
        old_mbid="d575d506-4da4-11e0-b951-0025225356f3",
    )
    rows = (
        ctx.db.get_fingerprint_db()
        .execute("SELECT track_id, mbid FROM track_mbid ORDER BY track_id, mbid")
        .fetchall()
    )
    expected_rows = [
        (1, UUID("77ef7468-e8f8-4447-9c7e-52b11272c6cc")),
        (1, UUID("97edb73c-4dac-11e0-9096-0025225356f3")),
        (1, UUID("b81f83ee-4da4-11e0-9ed8-0025225356f3")),
        (2, UUID("77ef7468-e8f8-4447-9c7e-52b11272c6cc")),
    ]
    assert expected_rows == rows


@with_script_context
def test_insert_track(ctx):
    # type: (ScriptContext) -> None
    id = insert_track(ctx.db.get_fingerprint_db())
    assert 5 == id
    id = insert_track(ctx.db.get_fingerprint_db())
    assert 6 == id


@with_script_context
def test_merge_tracks(ctx):
    # type: (ScriptContext) -> None
    prepare_database(
        ctx.db.get_fingerprint_db(),
        """
TRUNCATE track_mbid CASCADE;
INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
    VALUES (%(fp1)s, %(len1)s, 1, 1), (%(fp2)s, %(len2)s, 2, 1);
INSERT INTO track_mbid (id, track_id, mbid, submission_count) VALUES (1, 1, '97edb73c-4dac-11e0-9096-0025225356f3', 10);
INSERT INTO track_mbid (id, track_id, mbid, submission_count) VALUES (2, 1, 'd575d506-4da4-11e0-b951-0025225356f3', 15);
INSERT INTO track_mbid (id, track_id, mbid, submission_count) VALUES (3, 2, 'd575d506-4da4-11e0-b951-0025225356f3', 50);
INSERT INTO track_mbid (id, track_id, mbid, submission_count) VALUES (4, 3, '97edb73c-4dac-11e0-9096-0025225356f3', 25);
INSERT INTO track_mbid (id, track_id, mbid, submission_count) VALUES (5, 4, '5d0290a6-4dad-11e0-a47a-0025225356f3', 30);
INSERT INTO track_puid (track_id, puid, submission_count) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f4', 10);
INSERT INTO track_puid (track_id, puid, submission_count) VALUES (1, 'd575d506-4da4-11e0-b951-0025225356f4', 15);
INSERT INTO track_puid (track_id, puid, submission_count) VALUES (2, 'd575d506-4da4-11e0-b951-0025225356f4', 50);
INSERT INTO track_puid (track_id, puid, submission_count) VALUES (3, '97edb73c-4dac-11e0-9096-0025225356f4', 25);
INSERT INTO track_puid (track_id, puid, submission_count) VALUES (4, '5d0290a6-4dad-11e0-a47a-0025225356f4', 30);
INSERT INTO track_mbid_change (track_mbid_id, account_id, disabled) VALUES (2, 1, true);
INSERT INTO track_mbid_change (track_mbid_id, account_id, disabled) VALUES (3, 1, true);
INSERT INTO track_mbid_change (track_mbid_id, account_id, disabled) VALUES (4, 1, true);
INSERT INTO track_mbid_change (track_mbid_id, account_id, disabled) VALUES (5, 1, true);
    """,
        dict(
            fp1=TEST_1A_FP_RAW,
            len1=TEST_1A_LENGTH,
            fp2=TEST_1B_FP_RAW,
            len2=TEST_1B_LENGTH,
        ),
    )

    merge_tracks(ctx.db.get_fingerprint_db(), ctx.db.get_ingest_db(), 3, [1, 2, 4])

    rows = (
        ctx.db.get_fingerprint_db()
        .execute("SELECT id, track_id FROM fingerprint ORDER BY id")
        .fetchall()
    )
    assert [(1, 3), (2, 3)] == rows

    rows = (
        ctx.db.get_fingerprint_db()
        .execute(
            "SELECT id, track_id, mbid, submission_count FROM track_mbid ORDER BY track_id, mbid"
        )
        .fetchall()
    )
    expected = [
        (5, 3, UUID("5d0290a6-4dad-11e0-a47a-0025225356f3"), 30),
        (1, 3, UUID("97edb73c-4dac-11e0-9096-0025225356f3"), 35),
        (2, 3, UUID("d575d506-4da4-11e0-b951-0025225356f3"), 65),
    ]
    assert expected == rows

    rows = (
        ctx.db.get_fingerprint_db()
        .execute(
            "SELECT track_id, puid, submission_count FROM track_puid ORDER BY track_id, puid"
        )
        .fetchall()
    )
    expected2 = [
        (3, UUID("5d0290a6-4dad-11e0-a47a-0025225356f4"), 30),
        (3, UUID("97edb73c-4dac-11e0-9096-0025225356f4"), 35),
        (3, UUID("d575d506-4da4-11e0-b951-0025225356f4"), 65),
    ]
    assert expected2 == rows

    rows = (
        ctx.db.get_fingerprint_db()
        .execute(
            "SELECT track_mbid_id, account_id FROM track_mbid_change ORDER BY track_mbid_id, account_id"
        )
        .fetchall()
    )
    expected_rows = [(1, 1), (2, 1), (2, 1), (5, 1)]
    assert expected_rows == rows

    rows = (
        ctx.db.get_fingerprint_db()
        .execute("SELECT id, new_id FROM track ORDER BY id, new_id")
        .fetchall()
    )
    assert [(1, 3), (2, 3), (3, None), (4, 3)] == rows


@with_script_context
def test_merge_tracks_disabled_target(ctx):
    # type: (ScriptContext) -> None
    prepare_database(
        ctx.db.get_fingerprint_db(),
        """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f3', 9, true);
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (2, '97edb73c-4dac-11e0-9096-0025225356f3', 11);
""",
    )
    merge_tracks(ctx.db.get_fingerprint_db(), ctx.db.get_ingest_db(), 1, [2])
    rows = (
        ctx.db.get_fingerprint_db()
        .execute(
            "SELECT track_id, mbid, submission_count, disabled FROM track_mbid ORDER BY track_id, mbid"
        )
        .fetchall()
    )
    expected_rows = [
        (1, UUID("97edb73c-4dac-11e0-9096-0025225356f3"), 20, False),
    ]
    assert expected_rows == rows


@with_script_context
def test_merge_tracks_disabled_source(ctx):
    # type: (ScriptContext) -> None
    prepare_database(
        ctx.db.get_fingerprint_db(),
        """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f3', 9);
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (2, '97edb73c-4dac-11e0-9096-0025225356f3', 11, true);
""",
    )
    merge_tracks(ctx.db.get_fingerprint_db(), ctx.db.get_ingest_db(), 1, [2])
    rows = (
        ctx.db.get_fingerprint_db()
        .execute(
            "SELECT track_id, mbid, submission_count, disabled FROM track_mbid ORDER BY track_id, mbid"
        )
        .fetchall()
    )
    expected_rows = [
        (1, UUID("97edb73c-4dac-11e0-9096-0025225356f3"), 20, False),
    ]
    assert expected_rows == rows


@with_script_context
def test_merge_tracks_disabled_both(ctx):
    # type: (ScriptContext) -> None
    prepare_database(
        ctx.db.get_fingerprint_db(),
        """
TRUNCATE track_mbid CASCADE;
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (1, '97edb73c-4dac-11e0-9096-0025225356f3', 9, true);
INSERT INTO track_mbid (track_id, mbid, submission_count, disabled) VALUES (2, '97edb73c-4dac-11e0-9096-0025225356f3', 11, true);
""",
    )
    merge_tracks(ctx.db.get_fingerprint_db(), ctx.db.get_ingest_db(), 1, [2])
    rows = (
        ctx.db.get_fingerprint_db()
        .execute(
            "SELECT track_id, mbid, submission_count, disabled FROM track_mbid ORDER BY track_id, mbid"
        )
        .fetchall()
    )
    expected_rows = [
        (1, UUID("97edb73c-4dac-11e0-9096-0025225356f3"), 20, True),
    ]
    assert expected_rows == rows


@with_script_context
def test_can_merge_tracks(ctx):
    # type: (ScriptContext) -> None
    prepare_database(
        ctx.db.get_fingerprint_db(),
        """
INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
    VALUES (%(fp1)s, %(len1)s, 1, 1), (%(fp2)s, %(len2)s, 2, 1),
           (%(fp3)s, %(len3)s, 3, 1);
    """,
        dict(
            fp1=TEST_1A_FP_RAW,
            len1=TEST_1A_LENGTH,
            fp2=TEST_1B_FP_RAW,
            len2=TEST_1B_LENGTH,
            fp3=TEST_2_FP_RAW,
            len3=TEST_2_LENGTH,
        ),
    )
    groups = can_merge_tracks(ctx.db.get_fingerprint_db(), [1, 2, 3])
    assert [set([1, 2])] == groups


@with_script_context
def test_can_add_fp_to_track(ctx):
    # type: (ScriptContext) -> None
    prepare_database(
        ctx.db.get_fingerprint_db(),
        """
INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
    VALUES (%(fp1)s, %(len1)s, 1, 1);
    """,
        dict(fp1=TEST_1A_FP_RAW, len1=TEST_1A_LENGTH),
    )
    res = can_add_fp_to_track(
        ctx.db.get_fingerprint_db(), 1, TEST_2_FP_RAW, TEST_2_LENGTH
    )
    assert res is False
    res = can_add_fp_to_track(
        ctx.db.get_fingerprint_db(), 1, TEST_1B_FP_RAW, TEST_1B_LENGTH + 20
    )
    assert res is False
    res = can_add_fp_to_track(
        ctx.db.get_fingerprint_db(), 1, TEST_1B_FP_RAW, TEST_1B_LENGTH
    )
    assert res is True
