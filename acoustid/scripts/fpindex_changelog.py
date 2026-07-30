# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Partition maintenance for fpindex_changelog.

The changelog is range-partitioned by month. Two jobs keep it healthy and they
fail in opposite directions, so they are deliberately independent:

  create ahead -- there is no DEFAULT partition (see acoustid.tables for why),
                  so a row with no partition to land in fails the INSERT, which
                  fails the importer's transaction. Nothing is lost -- the
                  submission stays in pending_submission and retries -- but the
                  import queue stops draining until a partition exists. A year
                  of runway is kept in front of the current month, so this takes
                  twelve months of unnoticed failure to reach.

  drop behind  -- retention. Dropping a whole partition keeps vacuum out of the
                  picture: rows are never updated or deleted, and partitions die
                  long before they reach freeze age.

Alert on HEADROOM, not on this job succeeding. A job that silently stops running
is exactly the case the headroom is defending against, and a green run tells you
nothing about next month.
"""

import datetime
import logging
import re

from sqlalchemy import sql
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from acoustid.script import Script
from acoustid.tables import (
    FPINDEX_CHANGELOG_CREATE_AHEAD_MONTHS,
    fpindex_changelog_add_months,
    fpindex_changelog_create_partition_sql,
    fpindex_changelog_month,
)

logger = logging.getLogger(__name__)


TABLE_NAME = "fpindex_changelog"

# Whole months to keep behind the current one, so between RETENTION_MONTHS and
# RETENTION_MONTHS + 1 months of log are on disk at any moment.
#
# This is how far back a consumer may resume from the log alone. Falling off the
# end is recoverable -- the node bootstraps from a peer snapshot instead -- so it
# is a tuning knob, not a correctness boundary. Keep it well past the point where
# a peer's own checkpoint would be too stale to donate. Note that the binding
# constraint is bytes, not rows: `query` holds an extracted query array, so a
# month is far larger on disk than its ~400k rows suggest.
RETENTION_MONTHS = 2

# Applied to the whole maintenance connection, not just to the drops.
#
# Measured on PG 17.4, not assumed: DROP TABLE <partition> and
# ALTER TABLE ... DETACH PARTITION take exactly the same locks -- ACCESS
# EXCLUSIVE on BOTH the parent and the partition. Creating a partition that does
# not exist yet takes ACCESS EXCLUSIVE on the parent as well. Each of those waits
# for every transaction currently touching fpindex_changelog, and while it waits
# it queues new writers behind it -- and the writers here are the trigger, which
# means fingerprint inserts stall for as long as the wait lasts.
#
# It is NOT enough that a partition is old and nobody wants its rows: opening a
# partitioned table locks ALL partitions at plan time, before pruning runs, so a
# consumer reading only this month's data still holds ACCESS SHARE on a partition
# from last year. Adding a `created` predicate does not help; this was tested.
# (Unrelated idle-in-transaction sessions that never touched the table do not
# block it.)
#
# What that means for the feed: a consumer must not hold a transaction open
# across a long-poll wait. Query, end the transaction, wait outside it, query
# again -- then the lock is held for milliseconds and an hourly retry finds a gap
# immediately. Hold it for a 20s poll window and every attempt collides.
#
# Hence a short timeout: give up rather than stall the feed, and try again next
# hour. In the steady state this costs nothing anyway -- the no-op
# CREATE TABLE IF NOT EXISTS calls, which is all but one of them a month, do not
# take the parent lock at all, because PostgreSQL checks for the relation before
# it locks.
LOCK_TIMEOUT = "1s"

_PARTITION_NAME_RE = re.compile(r"^fpindex_changelog_(\d{6})$")


def _server_today(conn: Connection) -> datetime.date:
    """Use the server's clock, not this process's.

    The partition key is clock_timestamp(), so the only calendar that matters
    is the database's.
    """
    return conn.execute(sql.text("SELECT current_date")).scalar_one()


def _existing_partitions(conn: Connection) -> dict[str, datetime.date]:
    """Monthly partitions of the changelog, by name.

    Only names matching the convention are returned, so nothing this job did
    not create can be dropped by it.
    """
    rows = conn.execute(
        sql.text(
            """
            SELECT c.relname
            FROM pg_inherits i
            JOIN pg_class c ON c.oid = i.inhrelid
            WHERE i.inhparent = to_regclass(:parent)
            """
        ),
        {"parent": TABLE_NAME},
    ).scalars()

    partitions = {}
    for name in rows:
        match = _PARTITION_NAME_RE.match(name)
        if match is None:
            continue
        partitions[name] = datetime.datetime.strptime(match.group(1), "%Y%m").date()
    return partitions


def _consecutive_months(months: set[datetime.date], start: datetime.date) -> int:
    """How many months run unbroken from `start`.

    Counting partitions would not do. A gap is the whole failure mode, and a
    gap in the middle of the runway deserves as much attention as a short one --
    but it leaves the count looking healthy.
    """
    count = 0
    month = start
    while month in months:
        count += 1
        month = fpindex_changelog_add_months(month, 1)
    return count


def create_partitions(conn: Connection, today: datetime.date) -> None:
    current = fpindex_changelog_month(today)
    for offset in range(FPINDEX_CHANGELOG_CREATE_AHEAD_MONTHS + 1):
        month = fpindex_changelog_add_months(current, offset)
        try:
            conn.execute(sql.text(fpindex_changelog_create_partition_sql(month)))
        except SQLAlchemyError:
            # Usually lock_timeout firing because something else is busy on the
            # table. Carry on rather than returning: the months after this one
            # are independent, and one that cannot be created right now should
            # not cost the entire year of runway behind it.
            logger.exception(
                "Failed to create changelog partition for %s", month.strftime("%Y-%m")
            )
            continue


def drop_partitions(conn: Connection, today: datetime.date) -> None:
    cutoff = fpindex_changelog_add_months(
        fpindex_changelog_month(today), -RETENTION_MONTHS
    )
    for name, month in sorted(_existing_partitions(conn).items(), key=lambda kv: kv[1]):
        if month >= cutoff:
            continue
        try:
            # Dropping the partition detaches it too, so this is one lock
            # acquisition rather than two.
            conn.execute(sql.text(f"DROP TABLE {name}"))
        except SQLAlchemyError:
            # Almost always lock_timeout firing because something else is busy
            # on the table. Harmless: the partition stays attached and readable,
            # and the next run tries again.
            logger.exception("Failed to drop changelog partition %s", name)
            continue
        logger.info("Dropped changelog partition %s", name)


def report_headroom(conn: Connection, today: datetime.date) -> int:
    """Months of unbroken partitions from the current one. Alert on this."""
    months = set(_existing_partitions(conn).values())
    headroom = _consecutive_months(months, fpindex_changelog_month(today))
    if headroom:
        logger.info("Changelog partition headroom: %d months", headroom)
    else:
        # With no default partition to catch them, fingerprint inserts are
        # failing right now.
        logger.error(
            "No changelog partition covers %s; fingerprint inserts are failing",
            today.strftime("%Y-%m"),
        )
    return headroom


def run_manage_fpindex_changelog(script: Script) -> None:
    engine = script.db_engines["fingerprint"]
    # Its own autocommit connection rather than the shared session: each DDL
    # statement should commit on its own, so a partition that cannot be dropped
    # right now does not roll back the partitions that were just created, and
    # nothing here holds a transaction open across the whole run.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(sql.text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
        today = _server_today(conn)
        create_partitions(conn, today)
        drop_partitions(conn, today)
        report_headroom(conn, today)
