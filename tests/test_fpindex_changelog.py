# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
import importlib.util
import os

import pytest
from sqlalchemy import sql
from sqlalchemy.exc import DatabaseError, OperationalError

import tests
from acoustid import tables
from acoustid.scripts.fpindex_changelog import (
    RETENTION_MONTHS,
    _consecutive_months,
    _existing_partitions,
    _server_today,
    create_partitions,
    drop_partitions,
    report_headroom,
)

# SQLSTATE lock_not_available -- what lock_timeout raises when a statement gives
# up waiting. Used here to observe blocking without threads or sleeps.
LOCK_NOT_AVAILABLE = "55P03"


INSERT_FINGERPRINT = """
    INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
    VALUES (:fingerprint, 100, 1, 1)
    RETURNING id
"""


def _fingerprint(seed):
    # type: (int) -> list[int]
    # acoustid_extract_query drops duplicates and the silence hash, so the
    # values have to actually differ for the extracted query to be non-empty.
    return [seed * 1000 + i for i in range(200)]


@pytest.fixture
def engine():
    assert tests.script is not None
    engine = tests.script.db_engines["fingerprint"]
    with engine.connect() as conn:
        conn.execute(sql.text("DELETE FROM fingerprint"))
        conn.execute(sql.text("DELETE FROM fpindex_changelog"))
        conn.commit()
    yield engine
    with engine.connect() as conn:
        conn.execute(sql.text("DELETE FROM fingerprint"))
        conn.execute(sql.text("DELETE FROM fpindex_changelog"))
        conn.commit()


def test_trigger_records_the_extracted_query(engine):
    """The log carries what the index is fed, not the raw fingerprint."""
    hashes = _fingerprint(1)
    with engine.connect() as conn:
        fingerprint_id = conn.execute(
            sql.text(INSERT_FINGERPRINT), {"fingerprint": hashes}
        ).scalar_one()
        conn.commit()

        row = conn.execute(
            sql.text("SELECT fingerprint_id, query FROM fpindex_changelog")
        ).one()
        expected = conn.execute(
            sql.text("SELECT acoustid_extract_query(:fp)"), {"fp": hashes}
        ).scalar_one()

    assert row.fingerprint_id == fingerprint_id
    assert row.query == expected
    assert len(row.query) > 0
    assert row.query != hashes


def test_second_writer_blocks_until_the_first_commits(engine):
    """The property the whole design rests on.

    Without pg_advisory_xact_lock in the trigger this test fails: the second
    writer would sail past, take a higher changelog id, and be free to commit
    before the first one -- leaving a lower id that appears in the log only
    after a consumer has already read past it, and is therefore skipped
    forever. That is the bug in the old index updater.
    """
    first = engine.connect()
    second = engine.connect()
    try:
        first.execute(sql.text(INSERT_FINGERPRINT), {"fingerprint": _fingerprint(1)})
        # Deliberately not committed: the advisory lock is held to end of
        # transaction, so the second writer must not get through.

        second.execute(sql.text("SET lock_timeout = '2s'"))
        with pytest.raises(OperationalError) as excinfo:
            second.execute(
                sql.text(INSERT_FINGERPRINT), {"fingerprint": _fingerprint(2)}
            )
        assert getattr(excinfo.value.orig, "pgcode", None) == LOCK_NOT_AVAILABLE

        second.rollback()
        first.commit()

        # Once the lock is released the same insert goes through, and lands
        # after the transaction that was holding it.
        second.execute(sql.text(INSERT_FINGERPRINT), {"fingerprint": _fingerprint(2)})
        second.commit()

        rows = first.execute(
            sql.text("SELECT id, fingerprint_id FROM fpindex_changelog ORDER BY id")
        ).all()
        assert len(rows) == 2
        assert rows[0].id < rows[1].id
    finally:
        first.close()
        second.close()


def test_changelog_ids_and_timestamps_advance_together(engine):
    """created must be monotonic in id, or time partitions and an id cursor
    disagree and the retained rows stop being a contiguous id range.

    The sequential case only. now() would satisfy this one too -- see
    test_created_follows_the_lock_not_the_transaction_start for the case that
    actually separates the two.
    """
    with engine.connect() as conn:
        for seed in range(5):
            conn.execute(
                sql.text(INSERT_FINGERPRINT), {"fingerprint": _fingerprint(seed)}
            )
            conn.commit()

        rows = conn.execute(
            sql.text("SELECT id, created, xid FROM fpindex_changelog ORDER BY id")
        ).all()

    assert len(rows) == 5
    assert [r.created for r in rows] == sorted(r.created for r in rows)
    assert all(r.xid is not None for r in rows)


def test_created_follows_the_lock_not_the_transaction_start(engine):
    """The case that distinguishes clock_timestamp() from now().

    Staged so the writer that takes the *later* changelog id has the *earlier*
    transaction start: `second` opens its transaction first, then `first` runs
    and commits, then `second` inserts. With now() the second row would carry
    the earlier timestamp despite the higher id -- and once created goes
    backwards against id, the rows a partition holds are no longer a contiguous
    id range, so retention would start cutting holes in the middle of the feed
    rather than off its tail.
    """
    first = engine.connect()
    second = engine.connect()
    try:
        # Opens second's transaction, fixing its now() before first inserts.
        second.execute(sql.text("SELECT 1"))

        first.execute(sql.text(INSERT_FINGERPRINT), {"fingerprint": _fingerprint(1)})
        first.commit()

        second.execute(sql.text(INSERT_FINGERPRINT), {"fingerprint": _fingerprint(2)})
        second.commit()

        rows = first.execute(
            sql.text("SELECT id, created FROM fpindex_changelog ORDER BY id")
        ).all()
    finally:
        first.close()
        second.close()

    assert len(rows) == 2
    assert rows[0].created < rows[1].created


def test_create_all_leaves_the_current_month_covered(engine):
    """The database the rest of the suite runs against is built by create_all,
    and with no DEFAULT partition every fingerprint insert in the whole suite
    depends on that hook having created this month. Asserted directly, because
    otherwise a break in it shows up as unrelated tests failing.

    It also pins tables.py and the maintenance task to the same naming: the
    task recognises partitions only by its own pattern, so a partition it
    cannot see is a partition it will neither count nor drop.
    """
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        today = _server_today(conn)
        name = tables.fpindex_changelog_partition_name(
            tables.fpindex_changelog_month(today)
        )
        assert name in _existing_partitions(conn)
        assert report_headroom(conn, today) >= 1


def test_insert_fails_loudly_when_no_partition_covers_today(engine):
    """The cost of having no DEFAULT partition, made explicit.

    This is the trade: rather than silently absorbing the row and blocking the
    partition that should have held it, the insert fails where someone will see
    it. The importer's transaction rolls back, pending_submission is untouched,
    and the submission retries once a partition exists.

    Safe to assert because DDL is transactional in PostgreSQL -- the DROP is
    rolled back with everything else, so the partition is still there
    afterwards.
    """
    with engine.connect() as conn:
        today = _server_today(conn)
        name = tables.fpindex_changelog_partition_name(
            tables.fpindex_changelog_month(today)
        )
        conn.execute(sql.text(f"DROP TABLE {name}"))
        with pytest.raises(DatabaseError) as excinfo:
            conn.execute(sql.text(INSERT_FINGERPRINT), {"fingerprint": _fingerprint(1)})
        assert "no partition of relation" in str(excinfo.value)
        conn.rollback()

    with engine.connect() as conn:
        assert name in _existing_partitions(conn)


def test_partitions_are_created_a_year_ahead(engine):
    """Exercised on a date far from today so it cannot collide with the
    partitions the test database actually needs."""
    today = datetime.date(2031, 6, 15)
    expected = ["fpindex_changelog_2031%02d" % month for month in range(6, 13)] + [
        "fpindex_changelog_2032%02d" % month for month in range(1, 7)
    ]
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        try:
            create_partitions(conn, today)
            partitions = _existing_partitions(conn)

            assert set(expected) <= set(partitions)
            assert partitions["fpindex_changelog_203106"] == datetime.date(2031, 6, 1)
            # A year of runway, counted as consecutive months rather than as a
            # total, so a hole in the middle cannot pass for a full tank.
            assert report_headroom(conn, today) == 13
        finally:
            for name in expected:
                conn.execute(sql.text(f"DROP TABLE IF EXISTS {name}"))


def test_partitions_past_retention_are_dropped(engine):
    """Run against the real current month, because the thing most likely to go
    wrong with a cutoff is that it takes the live partition with it."""
    old = [datetime.date(2020, 1, 1), datetime.date(2020, 2, 1)]
    old_names = [tables.fpindex_changelog_partition_name(month) for month in old]
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        today = _server_today(conn)
        current = tables.fpindex_changelog_partition_name(
            tables.fpindex_changelog_month(today)
        )
        try:
            for month in old:
                conn.execute(
                    sql.text(tables.fpindex_changelog_create_partition_sql(month))
                )
            assert set(old_names) <= set(_existing_partitions(conn))

            drop_partitions(conn, today)

            remaining = set(_existing_partitions(conn))
            assert not (remaining & set(old_names))
            assert current in remaining
        finally:
            for name in old_names:
                conn.execute(sql.text(f"DROP TABLE IF EXISTS {name}"))


def test_retention_keeps_whole_months_behind_the_current_one(engine):
    """A partition is only dropped once its entire month is past the cutoff, so
    the log always reaches back at least RETENTION_MONTHS."""
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        today = _server_today(conn)
        current = tables.fpindex_changelog_month(today)
        boundary = tables.fpindex_changelog_add_months(current, -RETENTION_MONTHS)
        names = [
            tables.fpindex_changelog_partition_name(boundary),
            tables.fpindex_changelog_partition_name(
                tables.fpindex_changelog_add_months(boundary, -1)
            ),
        ]
        try:
            for name, month in zip(
                names, [boundary, tables.fpindex_changelog_add_months(boundary, -1)]
            ):
                conn.execute(
                    sql.text(tables.fpindex_changelog_create_partition_sql(month))
                )

            drop_partitions(conn, today)

            remaining = set(_existing_partitions(conn))
            # Exactly on the cutoff survives; one month older does not.
            assert names[0] in remaining
            assert names[1] not in remaining
        finally:
            for name in names:
                conn.execute(sql.text(f"DROP TABLE IF EXISTS {name}"))


def test_headroom_stops_at_the_first_gap():
    """Pure, because the interesting case is hard to stage against a live
    database without dropping a partition the rest of the suite needs.

    A gap is the failure mode create_partitions is written to survive -- it
    carries on past a month it could not create -- so headroom has to notice
    one. A plain count of future partitions would not.
    """
    months = {
        datetime.date(2026, 7, 1),
        datetime.date(2026, 8, 1),
        # September missing.
        datetime.date(2026, 10, 1),
        datetime.date(2026, 11, 1),
    }
    assert _consecutive_months(months, datetime.date(2026, 7, 1)) == 2
    assert _consecutive_months(months, datetime.date(2026, 10, 1)) == 2
    assert _consecutive_months(months, datetime.date(2026, 9, 1)) == 0


def test_month_arithmetic_crosses_year_boundaries():
    add_months = tables.fpindex_changelog_add_months
    assert add_months(datetime.date(2026, 12, 1), 1) == datetime.date(2027, 1, 1)
    assert add_months(datetime.date(2026, 1, 1), -1) == datetime.date(2025, 12, 1)
    assert add_months(datetime.date(2026, 7, 1), 12) == datetime.date(2027, 7, 1)
    assert add_months(datetime.date(2026, 7, 1), 0) == datetime.date(2026, 7, 1)
    assert tables.fpindex_changelog_month(datetime.date(2026, 7, 31)) == datetime.date(
        2026, 7, 1
    )


# Path rather than an import: alembic versions are not a package, and a
# migration must never import acoustid.tables anyway -- it has to keep working
# as the models move, which is why the DDL is written out twice to begin with.
MIGRATION_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "alembic",
    "versions",
    "a1f4c72b90de_add_fpindex_changelog.py",
)


def test_migration_and_models_agree_on_the_advisory_lock_key():
    """The one duplication that fails silently and catastrophically.

    The trigger DDL is deliberately written out twice -- once in tables.py for
    create_all, once in the migration -- because a migration must not import the
    models. Most drift between the two would surface as an obvious schema
    mismatch. A divergent lock key would not: writers would take two *different*
    advisory locks, stop serialising against each other, and the skipped-row gap
    this whole changelog exists to close would quietly come back, with every
    test still passing.
    """
    spec = importlib.util.spec_from_file_location("fpindex_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.LOCK_KEY == tables.FPINDEX_CHANGELOG_LOCK_KEY
    # And that the key each side actually emits is that constant, not a literal
    # that drifted away from it.
    assert str(tables.FPINDEX_CHANGELOG_LOCK_KEY) in tables.FPINDEX_CHANGELOG_DDL
