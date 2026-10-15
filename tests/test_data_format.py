# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from unittest import mock

from sqlalchemy import sql

from acoustid.data.format import find_or_insert_format
from tests import with_database


@with_database
def test_find_or_insert_format(conn):
    id = find_or_insert_format(conn, "FLAC")
    assert 1 == id
    id = find_or_insert_format(conn, "MP3")
    assert 2 == id
    rows = conn.execute(sql.text("SELECT id, name FROM format ORDER BY id")).all()
    expected_rows = [
        (1, "FLAC"),
        (2, "MP3"),
    ]
    assert expected_rows == rows


def count_named(conn, name):
    return conn.execute(
        sql.text("SELECT count(*) FROM format WHERE name = :name"), {"name": name}
    ).scalar()


@with_database
def test_find_or_insert_format_is_idempotent(conn):
    first = find_or_insert_format(conn, "Monkey's Audio")
    assert first == find_or_insert_format(conn, "Monkey's Audio")
    assert 1 == count_named(conn, "Monkey's Audio")


@with_database
def test_find_or_insert_format_survives_a_concurrent_insert(conn):
    """Two importers can both miss the initial select for a name neither has
    seen, and the unique index then rejects the second insert.

    The select is stubbed to miss while the row exists, which is the state a
    racing importer leaves behind between our select and our insert.
    """
    existing = find_or_insert_format(conn, "PCM_S16LE")

    real_execute = conn.execute
    missed: list[bool] = []

    def execute_with_one_missed_select(statement, *args, **kwargs):
        result = real_execute(statement, *args, **kwargs)
        if not missed and "SELECT" in str(statement).upper():
            missed.append(True)
            return _Missed()
        return result

    class _Missed:
        def scalar(self):
            return None

    with mock.patch.object(conn, "execute", execute_with_one_missed_select):
        again = find_or_insert_format(conn, "PCM_S16LE")

    assert again == existing
    assert 1 == count_named(conn, "PCM_S16LE")
