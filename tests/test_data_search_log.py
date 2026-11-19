# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Tests for search logging, and for the retention that ships with it."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import sql

from acoustid import tables as schema
from acoustid.data.search_log import (
    SESSION_HASH_LENGTH,
    delete_old_searches,
    hash_session_token,
    insert_search_click,
    insert_search_query,
)
from acoustid.db import AppDB

from . import with_database

SECRET = "a-secret"
MBID = "b1a9c0e9-d987-4042-ae91-78d6a3267d69"


def test_session_hash_is_stable_within_a_day() -> None:
    """Two searches by one visitor on one day must group together."""
    day = date(2026, 10, 16)
    first = hash_session_token(SECRET, "token-abc", day)
    second = hash_session_token(SECRET, "token-abc", day)
    assert first == second
    assert first is not None
    assert len(first) == SESSION_HASH_LENGTH


def test_session_hash_changes_the_next_day() -> None:
    """The rotation, which is the entire privacy property.

    If this ever returns equal values, the hashes become a stable identifier
    and the log becomes a history of one person rather than a day's activity.
    """
    yesterday = hash_session_token(SECRET, "token-abc", date(2026, 10, 15))
    today = hash_session_token(SECRET, "token-abc", date(2026, 10, 16))
    assert yesterday != today


def test_session_hash_distinguishes_visitors() -> None:
    day = date(2026, 10, 16)
    assert hash_session_token(SECRET, "token-a", day) != hash_session_token(
        SECRET, "token-b", day
    )


def test_session_hash_depends_on_the_secret() -> None:
    """Without this, the hash is a plain digest anyone could recompute."""
    day = date(2026, 10, 16)
    assert hash_session_token("one", "token-abc", day) != hash_session_token(
        "two", "token-abc", day
    )


def test_no_token_or_no_secret_hashes_to_nothing() -> None:
    """Both are ordinary cases: the query is still logged, ungrouped.

    Returning something made up instead would put every tokenless visitor
    under one shared identifier, which is worse than storing nothing.
    """
    day = date(2026, 10, 16)
    assert hash_session_token(SECRET, None, day) is None
    assert hash_session_token(SECRET, "", day) is None
    assert hash_session_token("", "token-abc", day) is None


def test_clicks_are_declared_to_cascade() -> None:
    """Asserted on the model, not on the database, and that distinction matters.

    The behavioural test below passes whatever `tables.py` declares, because
    the test schema is built with metadata.create_all, which is idempotent --
    an existing table keeps whatever constraints it was first created with. So
    only a fresh database would notice the declaration changing. Checking the
    model directly is environment-independent, and keeps `tables.py` in step
    with the migration, which is where production actually gets its schema
    from.
    """
    foreign_keys = list(schema.search_click.c.query_id.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].ondelete == "CASCADE"


@with_database
def test_insert_and_read_back_a_search(conn: AppDB) -> None:
    query_id = insert_search_query(conn, "queen bohemian rhapsody", 207, "deadbeef")
    row = conn.execute(
        sql.select(
            schema.search_query.c.query,
            schema.search_query.c.found,
            schema.search_query.c.session,
            schema.search_query.c.created,
        ).where(schema.search_query.c.id == query_id)
    ).one()
    assert row.query == "queen bohemian rhapsody"
    assert row.found == 207
    assert row.session == "deadbeef"
    assert row.created is not None


@with_database
def test_a_search_can_be_logged_without_a_session(conn: AppDB) -> None:
    query_id = insert_search_query(conn, "queen", 1, None)
    assert (
        conn.execute(
            sql.select(schema.search_query.c.session).where(
                schema.search_query.c.id == query_id
            )
        ).scalar_one()
        is None
    )


@with_database
def test_click_records_its_position(conn: AppDB) -> None:
    """Position is the point: a right answer at rank 7 is a ranking problem."""
    query_id = insert_search_query(conn, "queen", 207, None)
    insert_search_click(conn, query_id, MBID, 7)
    row = conn.execute(
        sql.select(
            schema.search_click.c.query_id,
            schema.search_click.c.mbid,
            schema.search_click.c.position,
        )
    ).one()
    assert row.query_id == query_id
    assert str(row.mbid) == MBID
    assert row.position == 7


@with_database
def test_retention_deletes_only_what_is_past_the_window(conn: AppDB) -> None:
    now = datetime.now(timezone.utc)
    old = insert_search_query(conn, "old query", 1, None)
    recent = insert_search_query(conn, "recent query", 1, None)
    conn.execute(
        schema.search_query.update()
        .where(schema.search_query.c.id == old)
        .values(created=now - timedelta(days=120))
    )

    deleted = delete_old_searches(conn, now - timedelta(days=90), 1000)

    assert deleted == 1
    remaining = conn.execute(sql.select(schema.search_query.c.id)).scalars().all()
    assert remaining == [recent]


@with_database
def test_retention_takes_clicks_with_it(conn: AppDB) -> None:
    """Clicks must not outlive the query they belong to.

    They carry the chosen recording and its position; left behind, they would
    be a residue of searches that have supposedly been forgotten.
    """
    now = datetime.now(timezone.utc)
    query_id = insert_search_query(conn, "old query", 1, None)
    insert_search_click(conn, query_id, MBID, 1)
    conn.execute(
        schema.search_query.update()
        .where(schema.search_query.c.id == query_id)
        .values(created=now - timedelta(days=120))
    )

    delete_old_searches(conn, now - timedelta(days=90), 1000)

    assert (
        conn.execute(sql.select(sql.func.count(schema.search_click.c.id))).scalar() == 0
    )


@with_database
def test_retention_respects_its_batch_limit(conn: AppDB) -> None:
    """Bounded per call, so cleanup is short transactions rather than one long one."""
    now = datetime.now(timezone.utc)
    for i in range(5):
        query_id = insert_search_query(conn, "old %d" % i, 1, None)
        conn.execute(
            schema.search_query.update()
            .where(schema.search_query.c.id == query_id)
            .values(created=now - timedelta(days=120))
        )

    assert delete_old_searches(conn, now - timedelta(days=90), 2) == 2
    assert delete_old_searches(conn, now - timedelta(days=90), 2) == 2
    assert delete_old_searches(conn, now - timedelta(days=90), 2) == 1
    assert delete_old_searches(conn, now - timedelta(days=90), 2) == 0
