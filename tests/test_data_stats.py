# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime

from acoustid.data.stats import find_application_lookup_stats, find_current_stats
from tests import prepare_database, with_database


@with_database
def test_find_current_stats(conn):
    prepare_database(
        conn,
        """
    INSERT INTO stats (name, value, date) VALUES
        ('account.all', 3, '2011-04-25'),
        ('account.all', 3, '2011-04-26'),
        ('account.all', 4, '2011-04-27'),
        ('track.all', 13, '2011-04-25'),
        ('track.all', 13, '2011-04-26'),
        ('track.all', 14, '2011-04-27');
    """,
    )
    stats = find_current_stats(conn)
    assert 4 == stats["account.all"]
    assert 14 == stats["track.all"]


@with_database
def test_find_application_lookup_stats_is_ordered_by_date(conn):
    today = datetime.date.today()
    days = [today - datetime.timedelta(days=n) for n in (2, 5, 1, 3)]
    for i, day in enumerate(days):
        prepare_database(
            conn,
            "INSERT INTO stats_lookups (date, hour, application_id, count_hits, count_nohits) "
            "VALUES (:date, 0, 1, :hits, 0)",
            {"date": day, "hits": i + 1},
        )
    stats = find_application_lookup_stats(conn, 1)
    assert [row["date"] for row in stats] == sorted(days)
