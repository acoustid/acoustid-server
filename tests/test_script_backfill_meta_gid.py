# Copyright (C) 2020 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import uuid

from acoustid import tables
from acoustid.data.submission import import_submission, insert_submission
from acoustid.script import ScriptContext
from acoustid.scripts.backfill_meta_gid import (
    backfill_meta_gid,
    get_last_meta_id,
    update_last_meta_id,
)

from . import (
    TEST_1_FP_RAW,
    TEST_1_LENGTH,
    TEST_2_FP_RAW,
    TEST_2_LENGTH,
    with_script_context,
)


@with_script_context
def test_get_update_last_meta_id(ctx):
    # type: (ScriptContext) -> None
    fingerprint_db = ctx.db.get_fingerprint_db()
    assert 0 == get_last_meta_id(fingerprint_db)
    assert 0 == get_last_meta_id(fingerprint_db)
    update_last_meta_id(fingerprint_db, 100)
    assert 100 == get_last_meta_id(fingerprint_db)
    update_last_meta_id(fingerprint_db, 101)
    assert 101 == get_last_meta_id(fingerprint_db)


@with_script_context
def test_backfill_meta_gid_update(ctx):
    app_db = ctx.db.get_app_db()
    fingerprint_db = ctx.db.get_fingerprint_db()
    ingest_db = ctx.db.get_ingest_db()

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
    query = tables.submission.select(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).fetchone()
    assert submission is not None

    fingerprint = import_submission(
        ingest_db, app_db, fingerprint_db, ctx.index, submission
    )
    assert fingerprint is not None

    query = tables.track_meta.select(
        tables.track_meta.c.track_id == fingerprint["track_id"]
    )
    track_meta = fingerprint_db.execute(query).fetchone()
    assert 1 == track_meta["submission_count"]

    query = (
        tables.meta.update()
        .values({"gid": None})
        .where(tables.meta.c.id == track_meta["meta_id"])
    )
    fingerprint_db.execute(query)

    query = tables.meta.select().where(tables.meta.c.id == track_meta["meta_id"])
    meta = fingerprint_db.execute(query).fetchone()
    assert meta["gid"] is None

    query = (
        tables.submission_result.update()
        .values({"meta_gid": None})
        .where(tables.submission_result.c.meta_id == track_meta["meta_id"])
    )
    ingest_db.execute(query)

    last_meta_id = backfill_meta_gid(fingerprint_db, ingest_db, 0, 100)
    assert 3 == last_meta_id

    query = tables.meta.select().where(tables.meta.c.id == track_meta["meta_id"])
    meta = fingerprint_db.execute(query).fetchone()
    assert uuid.UUID("da570fc1-ecfd-5fcd-86d7-009daa0f79e5") == meta["gid"]


@with_script_context
def test_backfill_meta_gid_merge(ctx):
    app_db = ctx.db.get_app_db()
    fingerprint_db = ctx.db.get_fingerprint_db()
    ingest_db = ctx.db.get_ingest_db()

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
    query = tables.submission.select(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).fetchone()
    assert submission is not None

    fingerprint = import_submission(
        ingest_db, app_db, fingerprint_db, ctx.index, submission
    )
    assert fingerprint is not None

    query = tables.track_meta.select(
        tables.track_meta.c.track_id == fingerprint["track_id"]
    )
    track_meta = fingerprint_db.execute(query).fetchone()
    assert 1 == track_meta["submission_count"]
    assert 3 == track_meta["meta_id"]

    query = tables.meta.select().where(tables.meta.c.id == track_meta["meta_id"])
    meta = fingerprint_db.execute(query).fetchone()
    assert uuid.UUID("da570fc1-ecfd-5fcd-86d7-009daa0f79e5") == meta["gid"]

    query = (
        tables.meta.update()
        .values({"gid": None})
        .where(tables.meta.c.id == track_meta["meta_id"])
    )
    fingerprint_db.execute(query)

    query = tables.meta.select().where(tables.meta.c.id == track_meta["meta_id"])
    meta = fingerprint_db.execute(query).fetchone()
    assert meta["gid"] is None

    submission_id = insert_submission(
        ingest_db,
        {
            "fingerprint": TEST_2_FP_RAW,
            "length": TEST_2_LENGTH,
            "bitrate": 192,
            "source_id": 1,
            "meta": {"track": "Foo"},
        },
    )
    query = tables.submission.select(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).fetchone()
    assert submission is not None

    fingerprint = import_submission(
        ingest_db, app_db, fingerprint_db, ctx.index, submission
    )
    assert fingerprint is not None

    last_meta_id = backfill_meta_gid(fingerprint_db, ingest_db, 0, 100)
    assert 4 == last_meta_id

    query = tables.track_meta.select(
        tables.track_meta.c.track_id == fingerprint["track_id"]
    )
    track_meta = fingerprint_db.execute(query).fetchone()
    assert 4 == track_meta["meta_id"]

    query = tables.meta.select().where(tables.meta.c.id == track_meta["meta_id"])
    meta = fingerprint_db.execute(query).fetchone()
    assert uuid.UUID("da570fc1-ecfd-5fcd-86d7-009daa0f79e5") == meta["gid"]


@with_script_context
def test_backfill_meta_gid_merge_duplicate(ctx):
    app_db = ctx.db.get_app_db()
    fingerprint_db = ctx.db.get_fingerprint_db()
    ingest_db = ctx.db.get_ingest_db()

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
    query = tables.submission.select(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).fetchone()
    assert submission is not None

    fingerprint = import_submission(
        ingest_db, app_db, fingerprint_db, ctx.index, submission
    )
    assert fingerprint is not None

    query = tables.track_meta.select(
        tables.track_meta.c.track_id == fingerprint["track_id"]
    )
    track_meta = fingerprint_db.execute(query).fetchone()
    assert 1 == track_meta["submission_count"]
    assert 3 == track_meta["meta_id"]

    query = tables.meta.select().where(tables.meta.c.id == track_meta["meta_id"])
    meta = fingerprint_db.execute(query).fetchone()
    assert uuid.UUID("da570fc1-ecfd-5fcd-86d7-009daa0f79e5") == meta["gid"]

    query = (
        tables.meta.update()
        .values({"gid": None})
        .where(tables.meta.c.id == track_meta["meta_id"])
    )
    fingerprint_db.execute(query)

    query = tables.meta.select().where(tables.meta.c.id == track_meta["meta_id"])
    meta = fingerprint_db.execute(query).fetchone()
    assert meta["gid"] is None

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
    query = tables.submission.select(tables.submission.c.id == submission_id)
    submission = ingest_db.execute(query).fetchone()
    assert submission is not None

    fingerprint = import_submission(
        ingest_db, app_db, fingerprint_db, ctx.index, submission
    )
    assert fingerprint is not None

    last_meta_id = backfill_meta_gid(fingerprint_db, ingest_db, 0, 100)
    assert 4 == last_meta_id

    query = tables.track_meta.select(
        tables.track_meta.c.track_id == fingerprint["track_id"]
    )
    track_meta = fingerprint_db.execute(query).fetchone()
    assert 4 == track_meta["meta_id"]

    query = tables.meta.select().where(tables.meta.c.id == track_meta["meta_id"])
    meta = fingerprint_db.execute(query).fetchone()
    assert uuid.UUID("da570fc1-ecfd-5fcd-86d7-009daa0f79e5") == meta["gid"]
