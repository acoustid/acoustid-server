# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import uuid
from typing import Any

import pytest
from sqlalchemy import sql

from acoustid import tables
from acoustid.script import ScriptContext
from acoustid.scripts.claim_duplicate_gids import (
    DUPS_TABLE,
    PROGRESS_TABLE,
    ZERO_UUID,
    check_table_name,
    claim_batch,
    drop_progress,
    get_progress,
    init_progress,
    next_gid_bound,
    report,
)

from . import with_script_context

HIGH_GID = uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")


def create_dups(db: Any) -> None:
    db.execute(
        sql.text(
            "CREATE TABLE {t} (gid uuid, meta_ids integer[], n integer)".format(
                t=DUPS_TABLE
            )
        )
    )


def drop_all(db: Any) -> None:
    db.execute(sql.text("DROP TABLE IF EXISTS {t}".format(t=DUPS_TABLE)))
    drop_progress(db)


def add_meta(db: Any, values: dict[str, Any], gid: uuid.UUID | None = None) -> int:
    stmt = tables.meta.insert().values(gid=gid, **values).returning(tables.meta.c.id)
    return db.execute(stmt).scalar_one()


def add_group(db: Any, gid: uuid.UUID, meta_ids: list[int]) -> None:
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


def claim_all(db: Any) -> int:
    return claim_batch(db, ZERO_UUID, HIGH_GID)


@with_script_context
def test_lowest_member_takes_the_gid(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_dups(db)
        init_progress(db)
        gid = uuid.uuid4()
        first = add_meta(db, {"track": "Foo"})
        second = add_meta(db, {"track": "Foo"})
        third = add_meta(db, {"track": "Foo"})
        add_group(db, gid, [first, second, third])

        assert claim_all(db) == 1
        assert gid_of(db, first) == gid
        assert gid_of(db, second) is None
        assert gid_of(db, third) is None
    finally:
        drop_all(db)


@with_script_context
def test_an_existing_member_holder_keeps_it(ctx: ScriptContext) -> None:
    """Moving the gid would invalidate whatever is already grouped on it."""
    db = ctx.db.get_fingerprint_db()
    try:
        create_dups(db)
        init_progress(db)
        gid = uuid.uuid4()
        lowest = add_meta(db, {"track": "Foo"})
        holder = add_meta(db, {"track": "Foo"}, gid=gid)
        add_group(db, gid, [lowest, holder])

        assert claim_all(db) == 0
        assert gid_of(db, lowest) is None
        assert gid_of(db, holder) == gid
    finally:
        drop_all(db)


@with_script_context
def test_a_holder_outside_the_group_also_wins(ctx: ScriptContext) -> None:
    """The holder need not be a member.

    A row created after the snapshot with identical content holds the gid and
    is not in meta_ids at all -- the same situation as the singleton
    backfill's collisions.
    """
    db = ctx.db.get_fingerprint_db()
    try:
        create_dups(db)
        init_progress(db)
        gid = uuid.uuid4()
        first = add_meta(db, {"track": "Foo"})
        second = add_meta(db, {"track": "Foo"})
        add_group(db, gid, [first, second])
        newcomer = add_meta(db, {"track": "Foo"}, gid=gid)

        assert claim_all(db) == 0
        assert gid_of(db, first) is None
        assert gid_of(db, second) is None
        assert gid_of(db, newcomer) == gid
    finally:
        drop_all(db)


@with_script_context
def test_deleted_members_are_skipped(ctx: ScriptContext) -> None:
    """min(meta_ids) may name a row that no longer exists."""
    db = ctx.db.get_fingerprint_db()
    try:
        create_dups(db)
        init_progress(db)
        gid = uuid.uuid4()
        survivor = add_meta(db, {"track": "Foo"})
        add_group(db, gid, [survivor - 1000, survivor])

        assert claim_all(db) == 1
        assert gid_of(db, survivor) == gid
    finally:
        drop_all(db)


@with_script_context
def test_a_group_with_nothing_left_claims_nothing(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_dups(db)
        init_progress(db)
        add_group(db, uuid.uuid4(), [9_000_001, 9_000_002])

        assert claim_all(db) == 0
    finally:
        drop_all(db)


@with_script_context
def test_one_blocked_group_does_not_cost_the_others(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_dups(db)
        init_progress(db)
        taken = uuid.uuid4()
        blocked_low = add_meta(db, {"track": "Foo"})
        add_meta(db, {"track": "Foo"}, gid=taken)
        add_group(db, taken, [blocked_low])

        expected = []
        for n in range(3):
            gid = uuid.uuid4()
            low = add_meta(db, {"track": "Track %d" % n})
            add_meta(db, {"track": "Track %d" % n})
            add_group(db, gid, [low, low + 1])
            expected.append((low, gid))

        assert claim_all(db) == 3
        assert gid_of(db, blocked_low) is None
        for meta_id, gid in expected:
            assert gid_of(db, meta_id) == gid
    finally:
        drop_all(db)


@with_script_context
def test_claiming_is_idempotent(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_dups(db)
        init_progress(db)
        gid = uuid.uuid4()
        first = add_meta(db, {"track": "Foo"})
        second = add_meta(db, {"track": "Foo"})
        add_group(db, gid, [first, second])

        assert claim_all(db) == 1
        assert claim_all(db) == 0
        assert gid_of(db, first) == gid
    finally:
        drop_all(db)


@with_script_context
def test_nothing_is_merged_or_removed(ctx: ScriptContext) -> None:
    """Claiming leaves the group intact; merging is a separate step."""
    db = ctx.db.get_fingerprint_db()
    try:
        create_dups(db)
        init_progress(db)
        gid = uuid.uuid4()
        members = [add_meta(db, {"track": "Foo"}) for _ in range(4)]
        add_group(db, gid, members)

        claim_all(db)

        alive = db.execute(
            sql.select(sql.func.count())
            .select_from(tables.meta)
            .where(tables.meta.c.id.in_(members))
        ).scalar_one()
        assert alive == 4
        assert [gid_of(db, m) for m in members] == [gid, None, None, None]
    finally:
        drop_all(db)


@with_script_context
def test_cursor_moves_with_the_rows(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_dups(db)
        init_progress(db)
        assert get_progress(db) == (ZERO_UUID, 0)

        gid = uuid.uuid4()
        first = add_meta(db, {"track": "Foo"})
        add_group(db, gid, [first])
        claim_batch(db, ZERO_UUID, gid)

        last, claimed = get_progress(db)
        assert last == gid
        assert claimed == 1
    finally:
        drop_all(db)


@with_script_context
def test_only_groups_inside_the_bound_are_touched(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_dups(db)
        init_progress(db)
        low_gid = uuid.UUID("11111111-1111-4111-8111-111111111111")
        high_gid = uuid.UUID("22222222-2222-4222-8222-222222222222")
        low_member = add_meta(db, {"track": "Foo"})
        high_member = add_meta(db, {"track": "Bar"})
        add_group(db, low_gid, [low_member])
        add_group(db, high_gid, [high_member])

        assert claim_batch(db, ZERO_UUID, low_gid) == 1
        assert gid_of(db, low_member) == low_gid
        assert gid_of(db, high_member) is None
    finally:
        drop_all(db)


@with_script_context
def test_batch_bound_walks_in_gid_order(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_dups(db)
        gids = sorted(
            uuid.UUID("3333333%d-3333-4333-8333-333333333333" % n) for n in range(3)
        )
        for gid in gids:
            add_group(db, gid, [1])

        assert next_gid_bound(db, ZERO_UUID, 1) == gids[0]
        assert next_gid_bound(db, ZERO_UUID, 2) == gids[1]
        assert next_gid_bound(db, gids[0], 5) == gids[2]
        assert next_gid_bound(db, gids[2], 5) is None
    finally:
        drop_all(db)


@with_script_context
def test_report_counts_held_against_unheld(ctx: ScriptContext) -> None:
    db = ctx.db.get_fingerprint_db()
    try:
        create_dups(db)
        init_progress(db)
        held, unheld = uuid.uuid4(), uuid.uuid4()
        holder = add_meta(db, {"track": "Foo"}, gid=held)
        add_group(db, held, [holder])
        member = add_meta(db, {"track": "Bar"})
        add_group(db, unheld, [member])

        assert report(db) == (1, 1)
        claim_all(db)
        assert report(db) == (2, 0)
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
    assert check_table_name("tmp_meta_dups") == "tmp_meta_dups"
    with pytest.raises(ValueError):
        check_table_name("meta; DROP TABLE meta")
