# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import uuid
from typing import Any

import pytest
from sqlalchemy import sql

from acoustid import tables
from acoustid.script import ScriptContext
from acoustid.scripts.backfill_singleton_gids import (
    DUPS_TABLE,
    GID_TABLE,
    PROGRESS_TABLE,
    backfill_batch,
    check_table_name,
    drop_progress,
    get_progress,
    init_progress,
    last_snapshot_id,
    report,
)

from . import with_script_context


def create_scratch(db: Any) -> None:
    db.execute(
        sql.text(
            "CREATE TABLE {t} (id integer PRIMARY KEY, gid uuid NOT NULL)".format(
                t=GID_TABLE
            )
        )
    )
    db.execute(
        sql.text(
            "CREATE TABLE {t} (gid uuid, meta_ids integer[], n integer)".format(
                t=DUPS_TABLE
            )
        )
    )


def drop_scratch(db: Any) -> None:
    for table in (GID_TABLE, DUPS_TABLE):
        db.execute(sql.text("DROP TABLE IF EXISTS {t}".format(t=table)))
    drop_progress(db)


def add_meta(db: Any, values: dict[str, Any], gid: uuid.UUID | None = None) -> int:
    stmt = tables.meta.insert().values(gid=gid, **values).returning(tables.meta.c.id)
    return db.execute(stmt).scalar_one()


def add_computed(db: Any, meta_id: int, gid: uuid.UUID) -> None:
    db.execute(
        sql.text(
            "INSERT INTO {t} (id, gid) VALUES (:id, CAST(:gid AS uuid))".format(
                t=GID_TABLE
            )
        ),
        {"id": meta_id, "gid": str(gid)},
    )


def add_dup_group(db: Any, gid: uuid.UUID, meta_ids: list[int]) -> None:
    db.execute(
        sql.text(
            "INSERT INTO {t} (gid, meta_ids, n)"
            " VALUES (CAST(:gid AS uuid), CAST(:ids AS integer[]), :n)".format(
                t=DUPS_TABLE
            )
        ),
        {"gid": str(gid), "ids": meta_ids, "n": len(meta_ids)},
    )


def gid_of(db: Any, meta_id: int) -> uuid.UUID | None:
    return db.execute(
        sql.select(tables.meta.c.gid).where(tables.meta.c.id == meta_id)
    ).scalar_one()


@with_script_context
def test_gives_a_singleton_its_gid(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_scratch(db)
        init_progress(db)
        gid = uuid.uuid4()
        meta_id = add_meta(db, {"track": "Foo"})
        add_computed(db, meta_id, gid)

        assert backfill_batch(db, 0, meta_id + 1) == 1
        assert gid_of(db, meta_id) == gid
    finally:
        drop_scratch(db)


@with_script_context
def test_leaves_rows_in_duplicate_groups_alone(ctx: ScriptContext) -> None:
    """Only one row per group may hold the gid; that is the dedup's decision."""
    db = ctx.db.get_fingerprint_db()
    try:
        create_scratch(db)
        init_progress(db)
        gid = uuid.uuid4()
        first = add_meta(db, {"track": "Foo"})
        second = add_meta(db, {"track": "Foo"})
        add_computed(db, first, gid)
        add_computed(db, second, gid)
        add_dup_group(db, gid, [first, second])

        assert backfill_batch(db, 0, second + 1) == 0
        assert gid_of(db, first) is None
        assert gid_of(db, second) is None
    finally:
        drop_scratch(db)


@with_script_context
def test_skips_a_singleton_whose_gid_was_taken_since_the_snapshot(
    ctx: ScriptContext,
) -> None:
    """The collision case, and the reason the batch is guarded.

    A row created after the snapshot holds the gid our singleton computes to,
    because find_or_insert_meta looked it up, found nothing while our row's
    gid was still NULL, and inserted a content-identical row.
    """
    db = ctx.db.get_fingerprint_db()
    try:
        create_scratch(db)
        init_progress(db)
        gid = uuid.uuid4()
        old = add_meta(db, {"track": "Foo"})
        add_computed(db, old, gid)
        newcomer = add_meta(db, {"track": "Foo"}, gid=gid)

        # No exception, and the rest of the batch is unaffected.
        assert backfill_batch(db, 0, newcomer + 1) == 0
        assert gid_of(db, old) is None
        assert gid_of(db, newcomer) == gid
    finally:
        drop_scratch(db)


@with_script_context
def test_a_collision_does_not_cost_the_rest_of_the_batch(ctx: ScriptContext) -> None:
    """The whole point of guarding rather than catching."""
    db = ctx.db.get_fingerprint_db()
    try:
        create_scratch(db)
        init_progress(db)
        taken_gid = uuid.uuid4()
        blocked = add_meta(db, {"track": "Foo"})
        add_computed(db, blocked, taken_gid)
        add_meta(db, {"track": "Foo"}, gid=taken_gid)

        fine = []
        for n in range(3):
            gid = uuid.uuid4()
            meta_id = add_meta(db, {"track": "Track %d" % n})
            add_computed(db, meta_id, gid)
            fine.append((meta_id, gid))

        assert backfill_batch(db, 0, fine[-1][0] + 1) == 3
        assert gid_of(db, blocked) is None
        for meta_id, gid in fine:
            assert gid_of(db, meta_id) == gid
    finally:
        drop_scratch(db)


@with_script_context
def test_leaves_rows_that_already_have_a_gid_untouched(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_scratch(db)
        init_progress(db)
        existing = uuid.uuid4()
        meta_id = add_meta(db, {"track": "Foo"}, gid=existing)
        add_computed(db, meta_id, uuid.uuid4())

        assert backfill_batch(db, 0, meta_id + 1) == 0
        assert gid_of(db, meta_id) == existing
    finally:
        drop_scratch(db)


@with_script_context
def test_cursor_moves_with_the_rows(ctx: ScriptContext) -> None:
    """Same transaction, so resuming cannot land behind the work."""
    db = ctx.db.get_fingerprint_db()
    try:
        create_scratch(db)
        init_progress(db)
        assert get_progress(db) == (0, 0)

        meta_id = add_meta(db, {"track": "Foo"})
        add_computed(db, meta_id, uuid.uuid4())
        backfill_batch(db, 0, meta_id + 1)

        last, written = get_progress(db)
        assert last == meta_id + 1
        assert written == 1

        # A second batch accumulates rather than replacing.
        backfill_batch(db, meta_id + 1, meta_id + 100)
        last, written = get_progress(db)
        assert last == meta_id + 100
        assert written == 1
    finally:
        drop_scratch(db)


@with_script_context
def test_batching_is_idempotent(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_scratch(db)
        init_progress(db)
        gid = uuid.uuid4()
        meta_id = add_meta(db, {"track": "Foo"})
        add_computed(db, meta_id, gid)

        assert backfill_batch(db, 0, meta_id + 1) == 1
        assert backfill_batch(db, 0, meta_id + 1) == 0
        assert gid_of(db, meta_id) == gid
    finally:
        drop_scratch(db)


@with_script_context
def test_only_the_requested_range_is_touched(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_scratch(db)
        init_progress(db)
        first_gid, second_gid = uuid.uuid4(), uuid.uuid4()
        first = add_meta(db, {"track": "Foo"})
        second = add_meta(db, {"track": "Bar"})
        add_computed(db, first, first_gid)
        add_computed(db, second, second_gid)

        assert backfill_batch(db, first, second) == 1
        assert gid_of(db, first) == first_gid
        assert gid_of(db, second) is None
    finally:
        drop_scratch(db)


@with_script_context
def test_report_separates_blocked_from_merely_unfinished(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_scratch(db)
        init_progress(db)

        taken_gid = uuid.uuid4()
        blocked = add_meta(db, {"track": "Foo"})
        add_computed(db, blocked, taken_gid)
        add_meta(db, {"track": "Foo"}, gid=taken_gid)

        pending = add_meta(db, {"track": "Bar"})
        add_computed(db, pending, uuid.uuid4())

        assert report(db) == (2, 1)

        backfill_batch(db, 0, pending + 1)
        # Only the blocked one is left, and it is reported as blocked.
        assert report(db) == (1, 1)
    finally:
        drop_scratch(db)


@with_script_context
def test_report_windows_agree_with_a_single_pass(ctx: ScriptContext) -> None:
    """Chunking is for locality, so it must not change the answer.

    The single-statement form does not finish on production -- every singleton
    surviving the dups anti-join is a random probe into meta_pkey across a
    95 GB table -- so report walks id windows instead.
    """
    db = ctx.db.get_fingerprint_db()
    try:
        create_scratch(db)
        init_progress(db)

        taken_gid = uuid.uuid4()
        blocked = add_meta(db, {"track": "Foo"})
        add_computed(db, blocked, taken_gid)
        add_meta(db, {"track": "Foo"}, gid=taken_gid)
        pending = [add_meta(db, {"track": "Track %d" % n}) for n in range(3)]
        for meta_id in pending:
            add_computed(db, meta_id, uuid.uuid4())

        whole = report(db, chunk_size=10**9)
        assert whole == (4, 1)
        # One row per window, and windows that hold nothing.
        assert report(db, chunk_size=1) == whole
        assert report(db, chunk_size=2) == whole
    finally:
        drop_scratch(db)


@with_script_context
def test_snapshot_end_is_where_the_walk_stops(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_scratch(db)
        assert last_snapshot_id(db) == 0
        meta_id = add_meta(db, {"track": "Foo"})
        add_computed(db, meta_id, uuid.uuid4())
        assert last_snapshot_id(db) == meta_id
    finally:
        drop_scratch(db)


@with_script_context
def test_get_progress_says_what_to_do_when_init_was_skipped(
    ctx: ScriptContext,
) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        init_progress(db)
        db.execute(sql.text("DELETE FROM {t}".format(t=PROGRESS_TABLE)))
        with pytest.raises(RuntimeError, match="run init first"):
            get_progress(db)
    finally:
        drop_progress(db)


def test_rejects_a_table_name_that_is_not_an_identifier() -> None:
    assert check_table_name("tmp_meta_gid") == "tmp_meta_gid"
    with pytest.raises(ValueError):
        check_table_name("meta; DROP TABLE meta")
