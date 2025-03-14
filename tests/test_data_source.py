# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from typing import cast

from sqlalchemy import Connection, sql

from acoustid.data.source import find_or_insert_source
from acoustid.db import AppDB
from tests import with_database


@with_database
def test_find_or_insert_source(conn: Connection) -> None:
    app_db = cast(AppDB, conn)

    rows = app_db.execute(
        sql.text("SELECT id, account_id, application_id FROM source ORDER BY id")
    ).all()
    expected_rows = [
        (1, 1, 1),
        (2, 2, 2),
    ]
    assert expected_rows == rows
    assert find_or_insert_source(app_db, 1, 1) == 1
    assert find_or_insert_source(app_db, 2, 2) == 2
    assert find_or_insert_source(app_db, 1, 2) == 3
    rows = app_db.execute(
        sql.text("SELECT id, account_id, application_id FROM source ORDER BY id")
    ).all()
    expected_rows = [
        (1, 1, 1),
        (2, 2, 2),
        (3, 2, 1),
    ]
    assert expected_rows == rows
