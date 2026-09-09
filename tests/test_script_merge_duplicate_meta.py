# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import uuid
from typing import Any

import pytest
from sqlalchemy import sql

from acoustid import tables
from acoustid.script import ScriptContext
from acoustid.scripts.merge_duplicate_meta import (
    GID_TABLE,
    PROGRESS_TABLE,
    check_table_name,
    clear_deferred,
    delete_duplicates,
    drop_progress,
    find_duplicates,
    get_deferred,
    get_progress,
    init_progress,
    last_snapshot_id,
    merge_batch,
    record_deferred,
    record_history,
    remaining,
    repoint_track_meta,
)

from . import with_script_context

HIGH = 10_000_000


def create_gid_table(db: Any) -> None:
    db.execute(
        sql.text(
            "CREATE TABLE {t} (id integer PRIMARY KEY, gid uuid NOT NULL)".format(
                t=GID_TABLE
            )
        )
    )


def drop_all(db: Any) -> None:
    db.execute(sql.text("DROP TABLE IF EXISTS {t}".format(t=GID_TABLE)))
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


def add_track(db: Any) -> int:
    return db.execute(
        tables.track.insert().values(gid=str(uuid.uuid4())).returning(tables.track.c.id)
    ).scalar_one()


def link(db: Any, track_id: int, meta_id: int, count: int = 1) -> int:
    return db.execute(
        tables.track_meta.insert()
        .values(track_id=track_id, meta_id=meta_id, submission_count=count)
        .returning(tables.track_meta.c.id)
    ).scalar_one()


def alive(db: Any, meta_ids: list[int]) -> set[int]:
    rows = db.execute(
        sql.select(tables.meta.c.id).where(tables.meta.c.id.in_(meta_ids))
    ).all()
    return {r.id for r in rows}


def track_meta_for(db: Any, track_ids: list[int]) -> list[Any]:
    return db.execute(
        sql.select(tables.track_meta)
        .where(tables.track_meta.c.track_id.in_(track_ids))
        .order_by(tables.track_meta.c.id)
    ).all()


def history_for(db: Any, meta_ids: list[int]) -> dict[int, uuid.UUID]:
    rows = db.execute(
        sql.select(tables.meta_id_history).where(
            tables.meta_id_history.c.id.in_(meta_ids)
        )
    ).all()
    return {r.id: r.gid for r in rows}


def a_claimed_group(db: Any, members: int = 2) -> tuple[uuid.UUID, int, list[int]]:
    """The state step 1 leaves: one row holds the gid, the rest are NULL."""
    gid = uuid.uuid4()
    primary = add_meta(db, {"track": "Foo"}, gid=gid)
    add_computed(db, primary, gid)
    losers = []
    for _ in range(members - 1):
        loser = add_meta(db, {"track": "Foo"})
        add_computed(db, loser, gid)
        losers.append(loser)
    return gid, primary, losers


@with_script_context
def test_merges_a_duplicate_into_the_row_holding_the_gid(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        gid, primary, (loser,) = a_claimed_group(db)
        track = add_track(db)
        link(db, track, loser)

        result = merge_batch(db, 0, HIGH)

        assert result.rows == 1
        assert alive(db, [primary, loser]) == {primary}
        assert history_for(db, [loser]) == {loser: gid}
        assert [r.meta_id for r in track_meta_for(db, [track])] == [primary]
    finally:
        drop_all(db)


@with_script_context
def test_needs_no_notion_of_a_group(ctx: ScriptContext) -> None:
    """Members are merged independently, in whatever order they are met.

    This is what claiming the gid first bought: the survivor is already
    decided, so two halves of one group can be merged in separate
    transactions without agreeing on anything.
    """
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        gid, primary, losers = a_claimed_group(db, members=5)
        assert len(losers) == 4

        # Split the group across two ranges that know nothing of each other.
        first = merge_batch(db, 0, losers[1] + 1)
        second = merge_batch(db, losers[1] + 1, HIGH)

        assert first.rows + second.rows == 4
        assert alive(db, [primary] + losers) == {primary}
        assert set(history_for(db, losers)) == set(losers)
    finally:
        drop_all(db)


@with_script_context
def test_folds_track_meta_that_would_collide(ctx: ScriptContext) -> None:
    """(track_id, meta_id) is unique, so a track referencing both must fold."""
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        gid, primary, (loser,) = a_claimed_group(db)
        track = add_track(db)
        kept = link(db, track, primary, count=2)
        link(db, track, loser, count=5)

        result = merge_batch(db, 0, HIGH)

        rows = track_meta_for(db, [track])
        assert len(rows) == 1
        assert rows[0].id == kept
        assert rows[0].submission_count == 7
        assert rows[0].updated is not None
        assert result.folded == 1
    finally:
        drop_all(db)


@with_script_context
def test_keeps_the_earliest_created_when_folding(ctx: ScriptContext) -> None:
    """meta.created is derived from min(track_meta.created) elsewhere."""
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        gid, primary, (loser,) = a_claimed_group(db)
        track = add_track(db)
        link(db, track, primary)
        old = link(db, track, loser)
        db.execute(
            tables.track_meta.update()
            .where(tables.track_meta.c.id == old)
            .values(created=sql.text("'2013-01-01 00:00:00+00'"))
        )

        merge_batch(db, 0, HIGH)

        assert track_meta_for(db, [track])[0].created.year == 2013
    finally:
        drop_all(db)


@with_script_context
def test_a_track_referencing_only_the_duplicate_is_repointed(
    ctx: ScriptContext,
) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        gid, primary, (loser,) = a_claimed_group(db)
        track = add_track(db)
        link(db, track, loser, count=3)

        result = merge_batch(db, 0, HIGH)

        rows = track_meta_for(db, [track])
        assert len(rows) == 1
        assert rows[0].meta_id == primary
        assert rows[0].submission_count == 3
        assert result.promoted == 1
        assert result.folded == 0
    finally:
        drop_all(db)


@with_script_context
def test_picks_up_a_singleton_the_gid_backfill_had_to_skip(
    ctx: ScriptContext,
) -> None:
    """The ~9,545 collisions, handled without knowing they are special.

    A row created after the snapshot took the gid, so the older row could not
    have it. That is exactly "no gid, and something else holds mine".
    """
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        gid = uuid.uuid4()
        old = add_meta(db, {"track": "Foo"})
        add_computed(db, old, gid)
        newcomer = add_meta(db, {"track": "Foo"}, gid=gid)

        merge_batch(db, 0, HIGH)

        assert alive(db, [old, newcomer]) == {newcomer}
        assert history_for(db, [old]) == {old: gid}
    finally:
        drop_all(db)


@with_script_context
def test_leaves_a_group_nobody_claimed_alone(ctx: ScriptContext) -> None:
    """With no row holding the gid there is no survivor to merge into."""
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        gid = uuid.uuid4()
        first = add_meta(db, {"track": "Foo"})
        second = add_meta(db, {"track": "Foo"})
        add_computed(db, first, gid)
        add_computed(db, second, gid)

        result = merge_batch(db, 0, HIGH)

        assert result.rows == 0
        assert alive(db, [first, second]) == {first, second}
        assert history_for(db, [first, second]) == {}
    finally:
        drop_all(db)


@with_script_context
def test_leaves_singletons_alone(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        gid = uuid.uuid4()
        only = add_meta(db, {"track": "Foo"}, gid=gid)
        add_computed(db, only, gid)

        assert merge_batch(db, 0, HIGH).rows == 0
        assert alive(db, [only]) == {only}
    finally:
        drop_all(db)


@with_script_context
def test_a_row_that_gains_a_reference_mid_merge_is_deferred_with_its_history(
    ctx: ScriptContext,
) -> None:
    """A submission can attach a track_meta row between the repoint and the delete.

    The delete is guarded, so that costs one skipped row rather than an
    aborted batch. History is already written by then, which is the ordering
    that matters: a crash or a skip leaves an id that still resolves, never
    one that has been deleted with no record of where it went.
    """
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        gid, primary, (loser,) = a_claimed_group(db)

        pairs = find_duplicates(db, 0, HIGH)
        record_history(db, pairs)
        repoint_track_meta(db, pairs)
        # Between the repoint and the delete, something references it again.
        link(db, add_track(db), loser)
        deleted = delete_duplicates(db, pairs)

        assert deleted == 0
        assert alive(db, [loser]) == {loser}
        assert history_for(db, [loser]) == {loser: gid}
    finally:
        drop_all(db)


@with_script_context
def test_merging_is_idempotent(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        gid, primary, (loser,) = a_claimed_group(db)
        track = add_track(db)
        link(db, track, primary, count=2)
        link(db, track, loser, count=5)

        assert merge_batch(db, 0, HIGH).rows == 1
        assert merge_batch(db, 0, HIGH).rows == 0
        rows = track_meta_for(db, [track])
        assert len(rows) == 1
        assert rows[0].submission_count == 7
    finally:
        drop_all(db)


@with_script_context
def test_only_the_requested_range_is_touched(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        gid_a, primary_a, (loser_a,) = a_claimed_group(db)
        gid_b, primary_b, (loser_b,) = a_claimed_group(db)

        merge_batch(db, 0, loser_a + 1)

        assert alive(db, [loser_a]) == set()
        assert alive(db, [loser_b]) == {loser_b}
    finally:
        drop_all(db)


@with_script_context
def test_cursor_moves_with_the_work(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        assert get_progress(db) == (0, 0)
        gid, primary, (loser,) = a_claimed_group(db)

        merge_batch(db, 0, HIGH)

        last, merged = get_progress(db)
        assert last == HIGH
        assert merged == 1
    finally:
        drop_all(db)


@with_script_context
def test_remaining_counts_what_is_left(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        a_claimed_group(db, members=3)

        assert remaining(db, 0, HIGH) == 2
        merge_batch(db, 0, HIGH)
        assert remaining(db, 0, HIGH) == 0
    finally:
        drop_all(db)


@with_script_context
def test_find_duplicates_pairs_each_row_with_its_primary(
    ctx: ScriptContext,
) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        gid, primary, losers = a_claimed_group(db, members=3)

        found = find_duplicates(db, 0, HIGH)

        assert sorted(f[0] for f in found) == sorted(losers)
        assert {f[1] for f in found} == {primary}
        assert {f[2] for f in found} == {gid}
    finally:
        drop_all(db)


@with_script_context
def test_snapshot_end_is_where_the_walk_stops(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        assert last_snapshot_id(db) == 0
        meta_id = add_meta(db, {"track": "Foo"})
        add_computed(db, meta_id, uuid.uuid4())
        assert last_snapshot_id(db) == meta_id
    finally:
        drop_all(db)


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


@with_script_context
def test_several_doomed_rows_on_one_track_collapse_into_one(
    ctx: ScriptContext,
) -> None:
    """The shape the large groups produce: one track, several doomed rows.

    This is what the DISTINCT ON promote is for. The lowest doomed row is
    moved onto the primary and the rest fold into it, summing as they go,
    because track_meta_idx_uniq would not have any of them side by side.
    """
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        _, primary, losers = a_claimed_group(db, members=4)
        track = add_track(db)
        for i, loser in enumerate(losers, start=1):
            link(db, track, loser, count=i)

        result = merge_batch(db, 0, HIGH)

        rows = track_meta_for(db, [track])
        assert len(rows) == 1
        assert rows[0].meta_id == primary
        assert rows[0].submission_count == 6
        assert result.promoted == 1
        assert result.folded == 2
        assert alive(db, [primary] + losers) == {primary}
    finally:
        drop_all(db)


@with_script_context
def test_a_row_whose_gid_points_at_different_content_is_left_alone(
    ctx: ScriptContext,
) -> None:
    """The gid table is prepared elsewhere, so being wrong is possible.

    Merging on a bad gid would move a row's metadata onto unrelated content
    and delete the original, which nothing could undo. Disagreeing rows are
    skipped instead, and stay visible to report.
    """
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        gid = uuid.uuid4()
        primary = add_meta(db, {"track": "Foo"}, gid=gid)
        add_computed(db, primary, gid)
        # The gid table claims this hashes to gid. Its content says otherwise.
        impostor = add_meta(db, {"track": "Something else entirely"})
        add_computed(db, impostor, gid)

        assert find_duplicates(db, 0, HIGH) == []

        result = merge_batch(db, 0, HIGH)

        assert result.rows == 0
        assert alive(db, [primary, impostor]) == {primary, impostor}
        assert history_for(db, [impostor]) == {}
        # Still counted, so the operator sees that something needs looking at.
        assert remaining(db, 0, HIGH) == 1
    finally:
        drop_all(db)


@with_script_context
def test_an_empty_string_is_the_same_content_as_null(ctx: ScriptContext) -> None:
    """generate_meta_gid skips falsy values, so the check has to as well.

    A row storing '' and a row storing NULL hash to the same gid and are
    genuinely duplicates. A strict comparison would refuse to merge exactly
    the rows the check exists to confirm.
    """
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        gid = uuid.uuid4()
        primary = add_meta(db, {"track": "Foo"}, gid=gid)
        add_computed(db, primary, gid)
        loser = add_meta(db, {"track": "Foo", "album": "", "track_no": 0})
        add_computed(db, loser, gid)

        result = merge_batch(db, 0, HIGH)

        assert result.rows == 1
        assert alive(db, [primary, loser]) == {primary}
    finally:
        drop_all(db)


@with_script_context
def test_a_deferred_range_is_remembered_until_a_sweep_clears_it(
    ctx: ScriptContext,
) -> None:
    """What the guard skips has to outlive the batch that skipped it.

    The cursor moves past the range regardless, so this table is the only
    record that the range is unfinished, and a clean pass over it is what
    removes the record.
    """
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        record_deferred(db, 0, HIGH, 3)
        record_deferred(db, HIGH, HIGH * 2, 1)

        assert get_deferred(db) == [(0, HIGH), (HIGH, HIGH * 2)]

        # Recording the same range again updates it rather than duplicating it.
        record_deferred(db, 0, HIGH, 2)
        assert get_deferred(db) == [(0, HIGH), (HIGH, HIGH * 2)]

        clear_deferred(db, 0)
        assert get_deferred(db) == [(HIGH, HIGH * 2)]
    finally:
        drop_all(db)


@with_script_context
def test_a_batch_with_nothing_left_clears_its_deferred_range(
    ctx: ScriptContext,
) -> None:
    """The sweep is a normal batch, and finishing is how it reports success."""
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        _, primary, (loser,) = a_claimed_group(db)
        record_deferred(db, 0, HIGH, 1)

        result = merge_batch(db, 0, HIGH)

        assert result.rows == 1
        assert result.deferred == 0
        assert get_deferred(db) == []
    finally:
        drop_all(db)


@with_script_context
def test_a_sweep_does_not_drag_the_cursor_backwards(ctx: ScriptContext) -> None:
    """Deferred ranges sit behind the cursor, and re-running one must not rewind it.

    Without greatest(), sweeping an early range would send the walk back over
    everything already merged.
    """
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        init_progress(db)
        db.execute(
            sql.text(
                "UPDATE {t} SET last_meta_id = :hi WHERE id = 1".format(
                    t=PROGRESS_TABLE
                )
            ),
            {"hi": HIGH},
        )

        merge_batch(db, 0, 10)

        last, _ = get_progress(db)
        assert last == HIGH
    finally:
        drop_all(db)


@with_script_context
def test_deferred_ranges_are_empty_before_init(ctx: ScriptContext) -> None:
    """report does not need init, and asking early should not raise."""
    db = ctx.db.get_fingerprint_db()
    try:
        create_gid_table(db)
        assert get_deferred(db) == []
    finally:
        drop_all(db)
