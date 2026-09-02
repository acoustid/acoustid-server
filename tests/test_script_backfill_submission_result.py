# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import uuid
from typing import Any

import pytest
from sqlalchemy import sql

from acoustid import tables
from acoustid.script import ScriptContext
from acoustid.scripts.backfill_submission_result import (
    GID_TABLE,
    PROGRESS_TABLE,
    Row,
    _batches,
    build_rows,
    check_table_name,
    claim_range,
    compare_batch,
    finish_range,
    init_queue,
    insert_rows,
    lookup_meta_gids,
    requeue_stale,
    watershed,
)

from . import with_script_context

MBID = uuid.UUID("97edb73c-4dac-11e0-9096-0025225356f3")
PUID = uuid.UUID("d575d506-4da4-11e0-b951-0025225356f3")


def create_gid_table(db: Any, table: str = GID_TABLE) -> None:
    db.execute(
        sql.text(
            "CREATE TABLE {t} (id integer PRIMARY KEY, gid uuid NOT NULL)".format(
                t=table
            )
        )
    )


def add_gid(db: Any, meta_id: int, gid: uuid.UUID, table: str = GID_TABLE) -> None:
    db.execute(
        sql.text(
            "INSERT INTO {t} (id, gid) VALUES (:id, CAST(:gid AS uuid))".format(t=table)
        ),
        {"id": meta_id, "gid": str(gid)},
    )


def insert_track(db: Any, new_id: int | None = None) -> int:
    stmt = (
        tables.track.insert()
        .values(gid=str(uuid.uuid4()), new_id=new_id)
        .returning(tables.track.c.id)
    )
    return db.execute(stmt).scalar_one()


def insert_fingerprint(db: Any, track_id: int) -> int:
    stmt = (
        tables.fingerprint.insert()
        .values(
            fingerprint=[1, 2, 3], length=100, track_id=track_id, submission_count=1
        )
        .returning(tables.fingerprint.c.id)
    )
    return db.execute(stmt).scalar_one()


def insert_fingerprint_source(
    db: Any, fingerprint_id: int, submission_id: int, source_id: int = 1
) -> None:
    db.execute(
        tables.fingerprint_source.insert().values(
            fingerprint_id=fingerprint_id,
            submission_id=submission_id,
            source_id=source_id,
        )
    )


def insert_meta_row(
    db: Any, values: dict[str, Any], gid: uuid.UUID | None = None
) -> int:
    stmt = tables.meta.insert().values(gid=gid, **values).returning(tables.meta.c.id)
    return db.execute(stmt).scalar_one()


def link_meta(db: Any, track_id: int, meta_id: int) -> int:
    stmt = (
        tables.track_meta.insert()
        .values(track_id=track_id, meta_id=meta_id, submission_count=1)
        .returning(tables.track_meta.c.id)
    )
    return db.execute(stmt).scalar_one()


def link_mbid(db: Any, track_id: int, mbid: uuid.UUID) -> int:
    stmt = (
        tables.track_mbid.insert()
        .values(track_id=track_id, mbid=mbid, submission_count=1)
        .returning(tables.track_mbid.c.id)
    )
    return db.execute(stmt).scalar_one()


def source_row(db: Any, track_meta_id: int, submission_id: int) -> None:
    db.execute(
        tables.track_meta_source.insert().values(
            track_meta_id=track_meta_id, submission_id=submission_id, source_id=1
        )
    )


def mbid_source_row(db: Any, track_mbid_id: int, submission_id: int) -> None:
    db.execute(
        tables.track_mbid_source.insert().values(
            track_mbid_id=track_mbid_id, submission_id=submission_id, source_id=1
        )
    )


def build(ctx: ScriptContext, ids: list[int]) -> tuple[list[Row], Any]:
    return build_rows(
        ctx.db.get_ingest_db(),
        ctx.db.get_fingerprint_db(),
        ctx.db.get_app_db(),
        ids,
    )


@with_script_context
def test_reconstructs_a_metadata_submission(ctx: ScriptContext) -> None:
    fingerprint_db = ctx.db.get_fingerprint_db()
    ingest_db = ctx.db.get_ingest_db()
    create_gid_table(fingerprint_db)

    gid = uuid.uuid4()
    track_id = insert_track(fingerprint_db)
    fingerprint_id = insert_fingerprint(fingerprint_db, track_id)
    meta_id = insert_meta_row(fingerprint_db, {"track": "Foo"})
    add_gid(fingerprint_db, meta_id, gid)
    track_meta_id = link_meta(fingerprint_db, track_id, meta_id)
    insert_fingerprint_source(ingest_db, fingerprint_id, 5000)
    source_row(ingest_db, track_meta_id, 5000)

    rows, skipped = build(ctx, [5000])

    assert skipped.total() == 0
    assert len(rows) == 1
    row = rows[0]
    assert row.submission_id == 5000
    assert row.fingerprint_id == fingerprint_id
    assert row.track_id == track_id
    assert row.meta_gid == gid
    assert row.mbid is None
    assert row.account_id == 1
    assert row.application_id == 1


@with_script_context
def test_reconstructs_an_mbid_submission_without_metadata(ctx: ScriptContext) -> None:
    """36% of the backlog is mbid or puid only; a null meta_gid is correct."""
    fingerprint_db = ctx.db.get_fingerprint_db()
    ingest_db = ctx.db.get_ingest_db()
    create_gid_table(fingerprint_db)

    track_id = insert_track(fingerprint_db)
    fingerprint_id = insert_fingerprint(fingerprint_db, track_id)
    track_mbid_id = link_mbid(fingerprint_db, track_id, MBID)
    insert_fingerprint_source(ingest_db, fingerprint_id, 5001)
    mbid_source_row(ingest_db, track_mbid_id, 5001)

    rows, _ = build(ctx, [5001])

    assert len(rows) == 1
    assert rows[0].mbid == MBID
    assert rows[0].meta_gid is None


@with_script_context
def test_prefers_metas_own_gid_over_the_snapshot(ctx: ScriptContext) -> None:
    fingerprint_db = ctx.db.get_fingerprint_db()
    ingest_db = ctx.db.get_ingest_db()
    create_gid_table(fingerprint_db)

    real_gid = uuid.uuid4()
    stale_gid = uuid.uuid4()
    track_id = insert_track(fingerprint_db)
    fingerprint_id = insert_fingerprint(fingerprint_db, track_id)
    meta_id = insert_meta_row(fingerprint_db, {"track": "Foo"}, gid=real_gid)
    add_gid(fingerprint_db, meta_id, stale_gid)
    track_meta_id = link_meta(fingerprint_db, track_id, meta_id)
    insert_fingerprint_source(ingest_db, fingerprint_id, 5002)
    source_row(ingest_db, track_meta_id, 5002)

    rows, _ = build(ctx, [5002])

    assert rows[0].meta_gid == real_gid


@with_script_context
def test_falls_back_to_the_snapshot_when_meta_has_no_gid(ctx: ScriptContext) -> None:
    fingerprint_db = ctx.db.get_fingerprint_db()
    create_gid_table(fingerprint_db)
    meta_id = insert_meta_row(fingerprint_db, {"track": "Foo"})
    gid = uuid.uuid4()
    add_gid(fingerprint_db, meta_id, gid)

    assert lookup_meta_gids(fingerprint_db, [meta_id]) == {meta_id: gid}


@with_script_context
def test_lowest_fingerprint_id_wins(ctx: ScriptContext) -> None:
    """A submission with several fingerprint_source rows resolves to one row."""
    fingerprint_db = ctx.db.get_fingerprint_db()
    ingest_db = ctx.db.get_ingest_db()
    create_gid_table(fingerprint_db)

    track_a = insert_track(fingerprint_db)
    track_b = insert_track(fingerprint_db)
    first = insert_fingerprint(fingerprint_db, track_a)
    second = insert_fingerprint(fingerprint_db, track_b)
    insert_fingerprint_source(ingest_db, second, 5003)
    insert_fingerprint_source(ingest_db, first, 5003)

    rows, _ = build(ctx, [5003])

    assert len(rows) == 1
    assert rows[0].fingerprint_id == min(first, second)
    assert rows[0].track_id == track_a


@with_script_context
def test_submissions_without_a_fingerprint_source_row_are_excluded(
    ctx: ScriptContext,
) -> None:
    """The ~9,920 orphans: metadata but no fingerprint, so not buildable."""
    fingerprint_db = ctx.db.get_fingerprint_db()
    ingest_db = ctx.db.get_ingest_db()
    create_gid_table(fingerprint_db)

    track_id = insert_track(fingerprint_db)
    meta_id = insert_meta_row(fingerprint_db, {"track": "Foo"})
    track_meta_id = link_meta(fingerprint_db, track_id, meta_id)
    source_row(ingest_db, track_meta_id, 5004)

    rows, skipped = build(ctx, [5004])

    assert rows == []
    assert skipped.total() == 0


@with_script_context
def test_insert_is_idempotent(ctx: ScriptContext) -> None:
    fingerprint_db = ctx.db.get_fingerprint_db()
    ingest_db = ctx.db.get_ingest_db()
    create_gid_table(fingerprint_db)

    track_id = insert_track(fingerprint_db)
    fingerprint_id = insert_fingerprint(fingerprint_db, track_id)
    insert_fingerprint_source(ingest_db, fingerprint_id, 5005)

    rows, _ = build(ctx, [5005])
    assert insert_rows(ingest_db, rows) == 1
    assert insert_rows(ingest_db, rows) == 0

    stored = ingest_db.execute(
        sql.select(tables.submission_result).where(
            tables.submission_result.c.submission_id == 5005
        )
    ).one()
    assert stored.track_id == track_id
    assert stored.handled_at is None


@with_script_context
def test_insert_counts_only_rows_actually_written(ctx: ScriptContext) -> None:
    """rows_written in the queue is how anyone judges whether a run worked."""
    fingerprint_db = ctx.db.get_fingerprint_db()
    ingest_db = ctx.db.get_ingest_db()
    create_gid_table(fingerprint_db)

    track_id = insert_track(fingerprint_db)
    for submission_id in range(5010, 5015):
        fingerprint_id = insert_fingerprint(fingerprint_db, track_id)
        insert_fingerprint_source(ingest_db, fingerprint_id, submission_id)
    rows, _ = build(ctx, list(range(5010, 5015)))
    assert len(rows) == 5

    assert insert_rows(ingest_db, rows[:3]) == 3
    # Three already there, two new: the count must be the two.
    assert insert_rows(ingest_db, rows) == 2
    assert insert_rows(ingest_db, rows) == 0


@with_script_context
def test_validate_accepts_a_correct_reconstruction(ctx: ScriptContext) -> None:
    fingerprint_db = ctx.db.get_fingerprint_db()
    ingest_db = ctx.db.get_ingest_db()
    create_gid_table(fingerprint_db)

    track_id = insert_track(fingerprint_db)
    fingerprint_id = insert_fingerprint(fingerprint_db, track_id)
    insert_fingerprint_source(ingest_db, fingerprint_id, 5006)

    rows, _ = build(ctx, [5006])
    insert_rows(ingest_db, rows)

    diff, records = compare_batch(ingest_db, fingerprint_db, rows)

    assert diff.compared == 1
    assert diff.mismatched == 0
    assert records == []


@with_script_context
def test_validate_catches_a_wrong_mapping(ctx: ScriptContext) -> None:
    """The point of the whole exercise: a bad column must be reported."""
    fingerprint_db = ctx.db.get_fingerprint_db()
    ingest_db = ctx.db.get_ingest_db()
    create_gid_table(fingerprint_db)

    track_id = insert_track(fingerprint_db)
    other_track = insert_track(fingerprint_db)
    fingerprint_id = insert_fingerprint(fingerprint_db, track_id)
    insert_fingerprint_source(ingest_db, fingerprint_id, 5007)

    rows, _ = build(ctx, [5007])
    insert_rows(ingest_db, rows)
    # The native row disagrees, and the tracks are unrelated.
    ingest_db.execute(
        tables.submission_result.update()
        .where(tables.submission_result.c.submission_id == 5007)
        .values(track_id=other_track, mbid=MBID)
    )

    diff, records = compare_batch(ingest_db, fingerprint_db, rows)

    assert diff.mismatched == 1
    assert diff.by_column["track_id"] == 1
    assert diff.by_column["mbid"] == 1
    assert diff.track_genuine == 1
    assert diff.track_merged == 0
    assert records[0]["submission_id"] == 5007


@with_script_context
def test_validate_separates_merged_tracks_from_real_errors(ctx: ScriptContext) -> None:
    """A track merged after import reads back as a different id, legitimately."""
    fingerprint_db = ctx.db.get_fingerprint_db()
    ingest_db = ctx.db.get_ingest_db()
    create_gid_table(fingerprint_db)

    target = insert_track(fingerprint_db)
    merged = insert_track(fingerprint_db, new_id=target)
    fingerprint_id = insert_fingerprint(fingerprint_db, target)
    insert_fingerprint_source(ingest_db, fingerprint_id, 5008)

    rows, _ = build(ctx, [5008])
    insert_rows(ingest_db, rows)
    # The native row names the track as it was before the merge.
    ingest_db.execute(
        tables.submission_result.update()
        .where(tables.submission_result.c.submission_id == 5008)
        .values(track_id=merged)
    )

    diff, _ = compare_batch(ingest_db, fingerprint_db, rows)

    assert diff.by_column["track_id"] == 1
    assert diff.track_merged == 1
    assert diff.track_genuine == 0


@with_script_context
def test_queue_hands_out_each_range_once(ctx: ScriptContext) -> None:
    ingest_db = ctx.db.get_ingest_db()
    try:
        assert init_queue(ingest_db, 0, 300, range_size=100) == 3

        claims = [claim_range(ingest_db, "w1") for _ in range(4)]
        assert claims[:3] == [(0, 100), (100, 200), (200, 300)]
        assert claims[3] is None

        finish_range(ingest_db, 0, written=10, skipped=1)
        state = ingest_db.execute(
            sql.text(
                "SELECT state, rows_written FROM {t} WHERE lo = 0".format(
                    t=PROGRESS_TABLE
                )
            )
        ).one()
        assert state.state == "done"
        assert state.rows_written == 10

        # A range still claimed but not recently is offered again.
        ingest_db.execute(
            sql.text(
                "UPDATE {t} SET claimed_at = now() - interval '1 day'"
                " WHERE lo = 100".format(t=PROGRESS_TABLE)
            )
        )
        assert requeue_stale(ingest_db, "6 hours") == 1
        assert claim_range(ingest_db, "w2") == (100, 200)
    finally:
        ingest_db.execute(sql.text("DROP TABLE IF EXISTS {t}".format(t=PROGRESS_TABLE)))


@with_script_context
def test_ranges_are_handed_out_lowest_first(ctx: ScriptContext) -> None:
    """A run starts on ids furthest below the watershed, so a bad run is
    confined to rows no native row occupies."""
    ingest_db = ctx.db.get_ingest_db()
    try:
        init_queue(ingest_db, 0, 500, range_size=100)
        claimed = [claim_range(ingest_db, "w1") for _ in range(5)]
        assert claimed == [(0, 100), (100, 200), (200, 300), (300, 400), (400, 500)]
    finally:
        ingest_db.execute(sql.text("DROP TABLE IF EXISTS {t}".format(t=PROGRESS_TABLE)))


def test_rejects_a_table_name_that_is_not_an_identifier() -> None:
    assert check_table_name("tmp_meta_gid") == "tmp_meta_gid"
    with pytest.raises(ValueError):
        check_table_name("meta; DROP TABLE meta")
    with pytest.raises(ValueError):
        check_table_name("")


@with_script_context
def test_init_queue_reports_only_the_ranges_it_added(ctx: ScriptContext) -> None:
    """Re-running init on a partly-filled queue must not claim old ranges."""
    ingest_db = ctx.db.get_ingest_db()
    try:
        assert init_queue(ingest_db, 0, 300, range_size=100) == 3
        assert init_queue(ingest_db, 0, 300, range_size=100) == 0
        assert init_queue(ingest_db, 0, 500, range_size=100) == 2
    finally:
        ingest_db.execute(sql.text("DROP TABLE IF EXISTS {t}".format(t=PROGRESS_TABLE)))


@with_script_context
def test_rejects_non_positive_sizes(ctx: ScriptContext) -> None:
    ingest_db = ctx.db.get_ingest_db()
    with pytest.raises(ValueError):
        init_queue(ingest_db, 0, 100, range_size=0)
    with pytest.raises(ValueError):
        list(_batches(0, 100, 0))


@with_script_context
def test_watershed_is_the_oldest_native_row(ctx: ScriptContext) -> None:
    ingest_db = ctx.db.get_ingest_db()
    assert watershed(ingest_db) is None
    ingest_db.execute(
        tables.submission_result.insert().values(
            submission_id=900,
            created=sql.func.now(),
            account_id=1,
            application_id=1,
            fingerprint_id=1,
            track_id=1,
        )
    )
    assert watershed(ingest_db) == 900
