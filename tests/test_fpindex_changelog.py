# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime

import pytest
from sqlalchemy import sql
from sqlalchemy.exc import OperationalError

import tests
from acoustid.scripts.fpindex_changelog import (
    _existing_partitions,
    check_default_partition,
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

    This is why the trigger uses clock_timestamp() and not now(): now() is
    transaction start time, so a slow transaction would file its row under an
    earlier timestamp than rows with lower ids.
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


def test_partitions_are_created_ahead_and_dropped_behind(engine):
    """Exercised on a date far from today so it cannot collide with the
    partitions a real deployment holds."""
    today = datetime.date(2031, 6, 15)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        created_names = []
        try:
            create_partitions(conn, today)
            partitions = _existing_partitions(conn)
            created_names = [name for name, day in partitions.items() if day >= today]

            assert partitions.get("fpindex_changelog_20310615") == today
            assert report_headroom(conn, today) >= 30

            # Nothing is old enough yet, so a drop pass must leave them alone.
            drop_partitions(conn, today)
            assert set(_existing_partitions(conn)) >= set(created_names)

            # Far enough in the future that every partition just made has
            # fallen entirely outside the retention window.
            later = today + datetime.timedelta(days=365)
            drop_partitions(conn, later)
            remaining = set(_existing_partitions(conn))
            assert not (remaining & set(created_names))
            created_names = []
        finally:
            for name in created_names:
                conn.execute(sql.text(f"DROP TABLE IF EXISTS {name}"))


def test_default_partition_is_reported_when_used(engine):
    """A row in the default partition means create-ahead fell behind. Writes
    still succeed -- that is the point of the backstop -- so this counter is
    the only thing that will tell anyone."""
    with engine.connect() as conn:
        conn.execute(sql.text(INSERT_FINGERPRINT), {"fingerprint": _fingerprint(1)})
        conn.commit()

    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        # No dated partition covers today in the test database, so the row can
        # only have landed in the default one.
        assert check_default_partition(conn) == 1
