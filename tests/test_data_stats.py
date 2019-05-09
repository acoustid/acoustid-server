# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import assert_equals
from tests import prepare_database, with_database
from acoustid.data.stats import (
    find_current_stats,
)


@with_database
def test_find_current_stats(conn):
    prepare_database(conn, """
    INSERT INTO stats (name, value, date) VALUES
        ('account.all', 3, '2011-04-25'),
        ('account.all', 3, '2011-04-26'),
        ('account.all', 4, '2011-04-27'),
        ('track.all', 13, '2011-04-25'),
        ('track.all', 13, '2011-04-26'),
        ('track.all', 14, '2011-04-27');
    """)
    stats = find_current_stats(conn)
    assert_equals(4, stats['account.all'])
    assert_equals(14, stats['track.all'])
