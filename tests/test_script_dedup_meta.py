# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""The set-based dedup has to agree with backfill_meta_gid, which is the
row-at-a-time version and defines the semantics."""

from typing import Any

import pytest
from sqlalchemy import sql

from acoustid.data.meta import generate_meta_gid
from acoustid.script import Script
from acoustid.scripts.dedup_meta import SOURCE_TABLE, dedup_meta

from . import with_script

# Two rows with the same metadata under different ids, and a third that is
# genuinely different.
DUPLICATE = {"track": "Mercy, Mercy, Mercy", "artist": "Ben Tankard"}
OTHER = {"track": "Heavenly Vibes", "artist": "Ben Tankard"}


def build_tmp_meta_gid(script: Script) -> None:
    """Stand in for the table built separately against production.

    Built here with generate_meta_gid, which is the definition the SQL version
    has to match, so the test is about the dedup and not about the hashing.
    """
    with script.context() as ctx:
        db = ctx.db.get_fingerprint_db()
        db.execute(sql.text("DROP TABLE IF EXISTS %s" % SOURCE_TABLE))
        db.execute(
            sql.text(
                "CREATE TABLE %s (id integer NOT NULL, gid uuid NOT NULL)"
                % SOURCE_TABLE
            )
        )
        rows = db.execute(
            sql.text(
                "SELECT id, track, artist, album, album_artist, track_no,"
                " disc_no, year FROM meta"
            )
        ).mappings()
        for row in rows:
            values = {k: v for k, v in row.items() if k != "id"}
            db.execute(
                sql.text("INSERT INTO %s (id, gid) VALUES (:id, :gid)" % SOURCE_TABLE),
                {"id": row["id"], "gid": str(generate_meta_gid(dict(values)))},
            )
        ctx.db.session.commit()


def insert_meta(db: Any, meta_id: int, values: dict, gid: object = None) -> None:
    db.execute(
        sql.text(
            "INSERT INTO meta (id, track, artist, gid) VALUES (:id, :track,"
            " :artist, :gid)"
        ),
        {
            "id": meta_id,
            "track": values.get("track"),
            "artist": values.get("artist"),
            "gid": gid,
        },
    )


def insert_track_meta(db: Any, tm_id: int, track_id: int, meta_id: int, count: int):
    db.execute(
        sql.text(
            "INSERT INTO track_meta (id, track_id, meta_id, submission_count)"
            " VALUES (:id, :track_id, :meta_id, :count)"
        ),
        {"id": tm_id, "track_id": track_id, "meta_id": meta_id, "count": count},
    )


def meta_rows(script: Script) -> dict:
    with script.context() as ctx:
        return {
            row[0]: row[1]
            for row in ctx.db.get_fingerprint_db().execute(
                sql.text("SELECT id, gid FROM meta ORDER BY id")
            )
        }


def track_meta_rows(script: Script) -> list:
    with script.context() as ctx:
        return [
            (row[0], row[1], row[2])
            for row in ctx.db.get_fingerprint_db().execute(
                sql.text(
                    "SELECT track_id, meta_id, submission_count FROM track_meta"
                    " ORDER BY track_id, meta_id"
                )
            )
        ]


@with_script
def test_duplicate_collapses_into_the_row_that_already_has_a_gid(
    script: Script,
) -> None:
    gid = generate_meta_gid(DUPLICATE)
    with script.context() as ctx:
        db = ctx.db.get_fingerprint_db()
        insert_meta(db, 9001, DUPLICATE, gid)  # already has one, so it survives
        insert_meta(db, 9002, DUPLICATE)  # even though its id is higher
        insert_meta(db, 9003, OTHER)
        ctx.db.session.commit()

    build_tmp_meta_gid(script)
    dedup_meta(script, chunk_size=1000, reset=True)

    rows = meta_rows(script)
    assert 9002 not in rows
    assert rows[9001] == gid
    assert rows[9003] == generate_meta_gid(OTHER)


@with_script
def test_survivor_is_the_lowest_id_when_none_has_a_gid(script: Script) -> None:
    with script.context() as ctx:
        db = ctx.db.get_fingerprint_db()
        insert_meta(db, 9005, DUPLICATE)
        insert_meta(db, 9004, DUPLICATE)
        insert_meta(db, 9006, DUPLICATE)
        ctx.db.session.commit()

    build_tmp_meta_gid(script)
    dedup_meta(script, chunk_size=1000, reset=True)

    rows = meta_rows(script)
    assert sorted(rows) == [1, 2, 9004]
    assert rows[9004] == generate_meta_gid(DUPLICATE)


@with_script
def test_deleted_ids_are_recorded_in_meta_id_history(script: Script) -> None:
    gid = generate_meta_gid(DUPLICATE)
    with script.context() as ctx:
        db = ctx.db.get_fingerprint_db()
        insert_meta(db, 9001, DUPLICATE, gid)
        insert_meta(db, 9002, DUPLICATE)
        ctx.db.session.commit()

    build_tmp_meta_gid(script)
    dedup_meta(script, chunk_size=1000, reset=True)

    with script.context() as ctx:
        history = {
            row[0]: row[1]
            for row in ctx.db.get_fingerprint_db().execute(
                sql.text("SELECT id, gid FROM meta_id_history")
            )
        }
    assert history == {9002: gid}


@with_script
def test_track_meta_is_repointed(script: Script) -> None:
    gid = generate_meta_gid(DUPLICATE)
    with script.context() as ctx:
        db = ctx.db.get_fingerprint_db()
        insert_meta(db, 9001, DUPLICATE, gid)
        insert_meta(db, 9002, DUPLICATE)
        insert_track_meta(db, 9101, 2, 9002, 3)
        ctx.db.session.commit()

    build_tmp_meta_gid(script)
    dedup_meta(script, chunk_size=1000, reset=True)

    assert (2, 9001, 3) in track_meta_rows(script)


@with_script
def test_track_linked_to_both_gets_one_row_with_the_counts_added(
    script: Script,
) -> None:
    """The unique index on (track_id, meta_id) makes plain repointing illegal
    here, so the two links have to become one."""
    gid = generate_meta_gid(DUPLICATE)
    with script.context() as ctx:
        db = ctx.db.get_fingerprint_db()
        insert_meta(db, 9001, DUPLICATE, gid)
        insert_meta(db, 9002, DUPLICATE)
        insert_track_meta(db, 9101, 2, 9001, 4)
        insert_track_meta(db, 9102, 2, 9002, 7)
        ctx.db.session.commit()

    build_tmp_meta_gid(script)
    dedup_meta(script, chunk_size=1000, reset=True)

    rows = [row for row in track_meta_rows(script) if row[0] == 2]
    assert rows == [(2, 9001, 11)]


@with_script
def test_track_linked_to_two_rows_that_both_disappear(script: Script) -> None:
    """Neither of the track's links is the survivor. The row-at-a-time version
    only reaches this case by accident, going one duplicate at a time."""
    with script.context() as ctx:
        db = ctx.db.get_fingerprint_db()
        insert_meta(db, 9004, DUPLICATE)
        insert_meta(db, 9005, DUPLICATE)
        insert_meta(db, 9006, DUPLICATE)
        insert_track_meta(db, 9101, 2, 9005, 2)
        insert_track_meta(db, 9102, 2, 9006, 5)
        ctx.db.session.commit()

    build_tmp_meta_gid(script)
    dedup_meta(script, chunk_size=1000, reset=True)

    rows = [row for row in track_meta_rows(script) if row[0] == 2]
    assert rows == [(2, 9004, 7)]


@with_script
def test_track_meta_updated_is_left_alone(script: Script) -> None:
    """Bumping it would move tens of millions of rows out of their own days in
    the rebuilt export and pile them into one."""
    gid = generate_meta_gid(DUPLICATE)
    with script.context() as ctx:
        db = ctx.db.get_fingerprint_db()
        insert_meta(db, 9001, DUPLICATE, gid)
        insert_meta(db, 9002, DUPLICATE)
        insert_track_meta(db, 9101, 2, 9001, 4)
        insert_track_meta(db, 9102, 2, 9002, 7)
        ctx.db.session.commit()

    build_tmp_meta_gid(script)
    dedup_meta(script, chunk_size=1000, reset=True)

    with script.context() as ctx:
        updated = (
            ctx.db.get_fingerprint_db()
            .execute(sql.text("SELECT updated FROM track_meta WHERE track_id = 2"))
            .scalars()
            .all()
        )
    assert updated == [None]


@with_script
def test_running_it_twice_changes_nothing(script: Script) -> None:
    gid = generate_meta_gid(DUPLICATE)
    with script.context() as ctx:
        db = ctx.db.get_fingerprint_db()
        insert_meta(db, 9001, DUPLICATE, gid)
        insert_meta(db, 9002, DUPLICATE)
        insert_track_meta(db, 9101, 2, 9001, 4)
        insert_track_meta(db, 9102, 2, 9002, 7)
        ctx.db.session.commit()

    build_tmp_meta_gid(script)
    dedup_meta(script, chunk_size=1000, reset=True)
    after_once = (meta_rows(script), track_meta_rows(script))
    dedup_meta(script, chunk_size=1000)
    assert (meta_rows(script), track_meta_rows(script)) == after_once


@with_script
def test_refuses_to_run_when_a_computed_gid_disagrees(script: Script) -> None:
    """A row that already has a gid is an oracle. If the recomputation does not
    reproduce it, the input is wrong and running on would merge rows that are
    not duplicates."""
    with script.context() as ctx:
        db = ctx.db.get_fingerprint_db()
        insert_meta(db, 9001, DUPLICATE, generate_meta_gid(OTHER))
        ctx.db.session.commit()

    build_tmp_meta_gid(script)
    with pytest.raises(RuntimeError, match="disagree"):
        dedup_meta(script, chunk_size=1000, reset=True)


@with_script
def test_refuses_to_run_when_the_input_is_incomplete(script: Script) -> None:
    with script.context() as ctx:
        db = ctx.db.get_fingerprint_db()
        insert_meta(db, 9001, DUPLICATE)
        ctx.db.session.commit()

    build_tmp_meta_gid(script)
    with script.context() as ctx:
        ctx.db.get_fingerprint_db().execute(
            sql.text("DELETE FROM %s WHERE id = 9001" % SOURCE_TABLE)
        )
        ctx.db.session.commit()

    with pytest.raises(RuntimeError, match="not finished"):
        dedup_meta(script, chunk_size=1000, reset=True)
