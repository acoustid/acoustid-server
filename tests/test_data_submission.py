# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import uuid

from sqlalchemy import select, text

from acoustid import const, tables
from acoustid.data.submission import (
    import_queued_submissions,
    import_submission,
    insert_submission,
)
from acoustid.script import ScriptContext
from tests import (
    TEST_1_FP_RAW,
    TEST_1_LENGTH,
    TEST_1A_FP_RAW,
    TEST_1A_LENGTH,
    TEST_1B_FP_RAW,
    TEST_1B_LENGTH,
    TEST_1C_FP_RAW,
    TEST_1C_LENGTH,
    TEST_1D_FP_RAW,
    TEST_1D_LENGTH,
    TEST_2_FP_RAW,
    TEST_2_LENGTH,
    prepare_database,
    with_script_context,
)


@with_script_context
def test_insert_submission(ctx):
    # type: (ScriptContext) -> None
    ingest_db = ctx.db.get_ingest_db()
    id = insert_submission(
        ingest_db,
        {
            "fingerprint": [1, 2, 3, 4, 5, 6],
            "length": 123,
            "bitrate": 192,
            "source_id": 1,
            "format_id": 1,
        },
    )
    assert 1 == id
    rows = ingest_db.execute(
        text(
            """
        SELECT fingerprint, length, bitrate, format_id
        FROM submission WHERE id=:id
    """
        ),
        {"id": id},
    ).fetchall()
    expected_rows = [
        ([1, 2, 3, 4, 5, 6], 123, 192, 1),
    ]
    assert expected_rows == rows


@with_script_context
def test_import_submission_with_meta(ctx):
    # type: (ScriptContext) -> None
    ingest_db = ctx.db.get_ingest_db()
    app_db = ctx.db.get_app_db()
    fingerprint_db = ctx.db.get_fingerprint_db()

    submission_id = insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_1_FP_RAW,
            "length": TEST_1_LENGTH,
            "bitrate": 192,
            "source_id": 1,
            "meta": {"track": "Foo"},
        },
    )
    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()

    fingerprint = import_submission(
        ingest_db, app_db, fingerprint_db, ctx.index, submission._mapping
    )

    assert fingerprint is not None

    query = select(tables.track_meta).where(
        tables.track_meta.c.track_id == fingerprint["track_id"]
    )
    track_meta = fingerprint_db.execute(query).one()
    assert 1 == track_meta.submission_count

    query = select(tables.meta).where(tables.meta.c.id == track_meta.meta_id)
    meta = fingerprint_db.execute(query).one()
    assert "Foo" == meta.track
    assert uuid.UUID("da570fc1-ecfd-5fcd-86d7-009daa0f79e5") == meta.gid


@with_script_context
def test_import_submission_with_foreignid(ctx):
    # type: (ScriptContext) -> None
    ingest_db = ctx.db.get_ingest_db()
    app_db = ctx.db.get_app_db()
    fingerprint_db = ctx.db.get_fingerprint_db()

    prepare_database(
        fingerprint_db,
        """
    INSERT INTO foreignid_vendor (id, name) VALUES (1, 'foo');
    INSERT INTO foreignid (id, vendor_id, name) VALUES (1, 1, '123');
    """,
    )

    submission_id = insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_1_FP_RAW,
            "length": TEST_1_LENGTH,
            "bitrate": 192,
            "source_id": 1,
            "format_id": 1,
            "foreignid_id": 1,
            "meta": {"track": "foo"},
        },
    )
    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()._mapping

    fingerprint = import_submission(
        ingest_db, app_db, fingerprint_db, ctx.index, submission._mapping
    )

    assert fingerprint is not None

    query = select(tables.track_foreignid).where(
        tables.track_foreignid.c.track_id == fingerprint["track_id"]
    )
    track_foreignid = fingerprint_db.execute(query).one()
    assert 1 == track_foreignid.submission_count

    submission_id = insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_1_FP_RAW,
            "length": TEST_1_LENGTH,
            "bitrate": 192,
            "source_id": 1,
            "format_id": 1,
            "foreignid": "foo:123",
            "meta": {"track": "foo"},
        },
    )
    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()._mapping

    fingerprint = import_submission(
        ingest_db, app_db, fingerprint_db, ctx.index, submission
    )

    assert fingerprint is not None

    query = select(tables.track_foreignid).where(
        tables.track_foreignid.c.track_id == fingerprint["track_id"]
    )
    track_foreignid = fingerprint_db.execute(query).one()
    assert 2 == track_foreignid.submission_count


@with_script_context
def test_import_submission(ctx):
    # type: (ScriptContext) -> None
    ingest_db = ctx.db.get_ingest_db()
    app_db = ctx.db.get_app_db()
    fingerprint_db = ctx.db.get_fingerprint_db()

    # first submission
    submission_id = insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_1_FP_RAW,
            "length": TEST_1_LENGTH,
            "bitrate": 192,
            "account_id": 1,
            "application_id": 1,
            "format": "FLAC",
            "mbid": "1f143d2b-db04-47cc-82a0-eee6efaa1142",
            "puid": "7c1c6753-c834-44b1-884a-a5166c093139",
        },
    )

    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()._mapping
    assert submission["handled"] is False

    fingerprint = import_submission(
        ingest_db, app_db, fingerprint_db, ctx.index, submission
    )

    assert fingerprint is not None
    assert 1 == fingerprint["id"]
    assert 5 == fingerprint["track_id"]

    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()._mapping
    assert submission["handled"] is True

    query = select(tables.track_mbid).where(
        tables.track_mbid.c.track_id == fingerprint["track_id"]
    )
    track_mbid = fingerprint_db.execute(query).one()._mapping
    assert 1 == track_mbid["submission_count"]

    query = select(tables.track_puid).where(
        tables.track_puid.c.track_id == fingerprint["track_id"]
    )
    track_puid = fingerprint_db.execute(query).one()._mapping
    assert 1 == track_puid["submission_count"]

    query = select(tables.fingerprint).where(
        tables.fingerprint.c.id == fingerprint["id"]
    )
    fingerprint2 = fingerprint_db.execute(query).one()._mapping
    assert fingerprint2 is not None
    assert 1 == fingerprint2["submission_count"]
    assert 1 == fingerprint2["format_id"]

    # second submission
    submission_id = insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_2_FP_RAW,
            "length": TEST_2_LENGTH,
            "bitrate": 192,
            "source_id": 1,
            "format_id": 1,
            "meta": {"track": "foo"},
        },
    )
    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()._mapping
    assert submission["handled"] is False

    fingerprint = import_submission(
        ingest_db, app_db, fingerprint_db, ctx.index, submission
    )
    assert fingerprint is not None
    assert 2 == fingerprint["id"]
    assert 6 == fingerprint["track_id"]

    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()._mapping
    assert submission["handled"] is True

    # third submission (same as the first one)
    submission_id = insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_1_FP_RAW,
            "length": TEST_1_LENGTH,
            "bitrate": 192,
            "source_id": 1,
            "format_id": 1,
            "mbid": "1f143d2b-db04-47cc-82a0-eee6efaa1142",
            "puid": "7c1c6753-c834-44b1-884a-a5166c093139",
        },
    )

    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()._mapping
    assert submission["handled"] is False

    fingerprint = import_submission(
        ingest_db, app_db, fingerprint_db, ctx.index, submission
    )
    assert fingerprint is not None
    assert 1 == fingerprint["id"]
    assert 5 == fingerprint["track_id"]

    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()._mapping
    assert submission["handled"] is True

    query = select(tables.track_mbid).where(
        tables.track_mbid.c.track_id == fingerprint["track_id"]
    )
    track_mbid = fingerprint_db.execute(query).one()._mapping
    assert 2 == track_mbid["submission_count"]

    query = select(tables.track_puid).where(
        tables.track_puid.c.track_id == fingerprint["track_id"]
    )
    track_puid = fingerprint_db.execute(query).one()._mapping
    assert 2 == track_puid["submission_count"]

    query = select(tables.fingerprint).where(
        tables.fingerprint.c.id == fingerprint["id"]
    )
    fingerprint2 = fingerprint_db.execute(query).one()._mapping
    assert fingerprint2 is not None
    assert 2 == fingerprint2["submission_count"]


@with_script_context
def test_import_submission_reuse_fingerprint_97(ctx):
    # type: (ScriptContext) -> None
    ingest_db = ctx.db.get_ingest_db()
    app_db = ctx.db.get_app_db()
    fingerprint_db = ctx.db.get_fingerprint_db()

    prepare_database(
        fingerprint_db,
        """
    INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
        VALUES (%(fp)s, %(len)s, 1, 1);
    """,
        dict(fp=TEST_1A_FP_RAW, len=TEST_1A_LENGTH),
    )

    submission_id = insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_1B_FP_RAW,
            "length": TEST_1B_LENGTH,
            "source_id": 1,
            "mbid": "1f143d2b-db04-47cc-82a0-eee6efaa1142",
            "puid": "7c1c6753-c834-44b1-884a-a5166c093139",
        },
    )

    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()._mapping
    assert submission["handled"] is False

    fingerprint = import_submission(
        ingest_db, app_db, fingerprint_db, ctx.index, submission
    )
    assert fingerprint is not None
    assert 1 == fingerprint["id"]
    assert 1 == fingerprint["track_id"]


@with_script_context
def test_import_submission_reuse_fingerprint_100(ctx):
    # type: (ScriptContext) -> None
    ingest_db = ctx.db.get_ingest_db()
    app_db = ctx.db.get_app_db()
    fingerprint_db = ctx.db.get_fingerprint_db()

    prepare_database(
        fingerprint_db,
        """
    INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
        VALUES (%(fp)s, %(len)s, 1, 1);
    """,
        dict(fp=TEST_1A_FP_RAW, len=TEST_1A_LENGTH),
    )

    submission_id = insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_1A_FP_RAW,
            "length": TEST_1A_LENGTH,
            "source_id": 1,
            "mbid": "1f143d2b-db04-47cc-82a0-eee6efaa1142",
            "puid": "7c1c6753-c834-44b1-884a-a5166c093139",
        },
    )

    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()._mapping
    assert submission["handled"] is False

    fingerprint = import_submission(
        ingest_db, app_db, fingerprint_db, ctx.index, submission
    )
    assert fingerprint is not None
    assert 1 == fingerprint["id"]
    assert 1 == fingerprint["track_id"]


@with_script_context
def test_import_submission_reuse_track_93(ctx):
    # type: (ScriptContext) -> None
    ingest_db = ctx.db.get_ingest_db()
    app_db = ctx.db.get_app_db()
    fingerprint_db = ctx.db.get_fingerprint_db()

    prepare_database(
        fingerprint_db,
        """
    INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
        VALUES (%(fp)s, %(len)s, 1, 1);
    """,
        dict(fp=TEST_1A_FP_RAW, len=TEST_1A_LENGTH),
    )

    submission_id = insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_1C_FP_RAW,
            "length": TEST_1C_LENGTH,
            "source_id": 1,
            "mbid": "1f143d2b-db04-47cc-82a0-eee6efaa1142",
            "puid": "7c1c6753-c834-44b1-884a-a5166c093139",
        },
    )

    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()._mapping
    assert submission["handled"] is False

    try:
        old_threshold = const.FINGERPRINT_MERGE_THRESHOLD
        const.FINGERPRINT_MERGE_THRESHOLD = 0.95
        fingerprint = import_submission(
            ingest_db, app_db, fingerprint_db, ctx.index, submission
        )
    finally:
        const.FINGERPRINT_MERGE_THRESHOLD = old_threshold
    assert fingerprint is not None
    assert 2 == fingerprint["id"]
    assert 1 == fingerprint["track_id"]


@with_script_context
def test_import_submission_new_track(ctx):
    # type: (ScriptContext) -> None
    ingest_db = ctx.db.get_ingest_db()
    app_db = ctx.db.get_app_db()
    fingerprint_db = ctx.db.get_fingerprint_db()

    prepare_database(
        fingerprint_db,
        """
    INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
        VALUES (%(fp)s, %(len)s, 1, 1);
    """,
        dict(fp=TEST_1A_FP_RAW, len=TEST_1A_LENGTH),
    )

    submission_id = insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_1D_FP_RAW,
            "length": TEST_1D_LENGTH,
            "source_id": 1,
            "mbid": "1f143d2b-db04-47cc-82a0-eee6efaa1142",
            "puid": "7c1c6753-c834-44b1-884a-a5166c093139",
        },
    )

    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()._mapping
    assert submission["handled"] is False

    try:
        old_threshold = const.TRACK_MERGE_THRESHOLD
        const.TRACK_MERGE_THRESHOLD = 0.9
        fingerprint = import_submission(
            ingest_db, app_db, fingerprint_db, ctx.index, submission
        )
    finally:
        const.TRACK_MERGE_THRESHOLD = old_threshold
    assert fingerprint is not None
    assert 2 == fingerprint["id"]
    assert 5 == fingerprint["track_id"]


@with_script_context
def test_import_submission_new_track_different(ctx):
    # type: (ScriptContext) -> None
    ingest_db = ctx.db.get_ingest_db()
    app_db = ctx.db.get_app_db()
    fingerprint_db = ctx.db.get_fingerprint_db()

    prepare_database(
        fingerprint_db,
        """
    INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
        VALUES (%(fp)s, %(len)s, 1, 1);
    """,
        dict(fp=TEST_1A_FP_RAW, len=TEST_1A_LENGTH),
    )

    submission_id = insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_2_FP_RAW,
            "length": TEST_2_LENGTH,
            "source_id": 1,
            "mbid": "1f143d2b-db04-47cc-82a0-eee6efaa1142",
            "puid": "7c1c6753-c834-44b1-884a-a5166c093139",
        },
    )

    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()._mapping
    assert submission["handled"] is False

    fingerprint = import_submission(
        ingest_db, app_db, fingerprint_db, ctx.index, submission
    )
    assert fingerprint is not None
    assert 2 == fingerprint["id"]
    assert 5 == fingerprint["track_id"]


@with_script_context
def test_import_submission_merge_existing_tracks(ctx):
    # type: (ScriptContext) -> None
    ingest_db = ctx.db.get_ingest_db()
    app_db = ctx.db.get_app_db()
    fingerprint_db = ctx.db.get_fingerprint_db()

    prepare_database(
        fingerprint_db,
        """
    INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
        VALUES (%(fp1)s, %(len1)s, 1, 1), (%(fp2)s, %(len2)s, 2, 1);
    """,
        dict(
            fp1=TEST_1A_FP_RAW,
            len1=TEST_1A_LENGTH,
            fp2=TEST_1B_FP_RAW,
            len2=TEST_1B_LENGTH,
        ),
    )

    submission_id = insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_1C_FP_RAW,
            "length": TEST_1C_LENGTH,
            "source_id": 1,
            "mbid": "1f143d2b-db04-47cc-82a0-eee6efaa1142",
            "puid": "7c1c6753-c834-44b1-884a-a5166c093139",
        },
    )

    query = select(tables.submission).where(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).one()._mapping
    assert submission["handled"] is False

    try:
        old_threshold = const.FINGERPRINT_MERGE_THRESHOLD
        const.FINGERPRINT_MERGE_THRESHOLD = 0.85
        fingerprint = import_submission(
            ingest_db, app_db, fingerprint_db, ctx.index, submission
        )
    finally:
        const.FINGERPRINT_MERGE_THRESHOLD = old_threshold

    assert fingerprint is not None
    assert 1 == fingerprint["id"]
    assert 1 == fingerprint["track_id"]

    query = select(tables.fingerprint).where(tables.fingerprint.c.id == 1)
    fingerprint = dict(fingerprint_db.execute(query).one())
    assert fingerprint is not None
    assert 1 == fingerprint["track_id"]

    query = select(tables.track).where(tables.track.c.id == 1)
    track = fingerprint_db.execute(query).one()._mapping
    assert track is not None
    assert track["new_id"] is None

    query = select(tables.track).where(tables.track.c.id == 2)
    track = fingerprint_db.execute(query).one()._mapping
    assert track is not None
    assert 1 == track["new_id"]


@with_script_context
def test_import_queued_submissions(ctx):
    # type: (ScriptContext) -> None
    ingest_db = ctx.db.get_ingest_db()
    app_db = ctx.db.get_app_db()
    fingerprint_db = ctx.db.get_fingerprint_db()

    insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_1_FP_RAW,
            "length": TEST_1_LENGTH,
            "bitrate": 192,
            "source_id": 1,
            "format_id": 1,
            "meta": {"track": "Foo"},
        },
    )
    insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_2_FP_RAW,
            "length": TEST_2_LENGTH,
            "bitrate": 192,
            "source_id": 1,
            "format_id": 1,
            "meta": {"track": "Foo 2"},
        },
    )
    insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_1_FP_RAW,
            "length": TEST_1_LENGTH,
            "bitrate": 192,
            "source_id": 1,
            "format_id": 1,
            "meta": {"track": "Foo 3"},
        },
    )

    import_queued_submissions(ingest_db, app_db, fingerprint_db, ctx.index)

    count = fingerprint_db.execute(
        text("SELECT count(*) FROM fingerprint WHERE id IN (1,2,3)")
    ).scalar()
    assert 2 == count

    count = fingerprint_db.execute(
        text("SELECT count(*) FROM track WHERE id IN (5,6,7)")
    ).scalar()
    assert 2 == count
