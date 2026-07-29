# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Partition maintenance for fpindex_changelog.

The changelog is range-partitioned by day. Two jobs keep it healthy and they
fail in opposite directions, so they are deliberately independent:

  create ahead -- a row with no partition to land in would fail the INSERT, and
                  that INSERT is a fingerprint submission. A DEFAULT partition
                  backstops it so writes never fail, but a row landing there
                  then blocks creating the dated partition that would have
                  covered it, so the default partition being non-empty is the
                  thing worth alerting on.

  drop behind  -- retention. Dropping a whole partition keeps vacuum out of the
                  picture: rows are never updated or deleted, and partitions die
                  long before they reach freeze age.

Alert on HEADROOM, not on this job succeeding. A job that silently stops running
is exactly the case the headroom is defending against, and a green run tells you
nothing about tomorrow.
"""

import datetime
import logging
import re

from sqlalchemy import sql
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from acoustid.script import Script

logger = logging.getLogger(__name__)


TABLE_NAME = "fpindex_changelog"
DEFAULT_PARTITION = "fpindex_changelog_default"

# Keep well ahead of any plausible outage of this job.
CREATE_AHEAD_DAYS = 30

# How far back a consumer may resume from the log alone. Falling off the end is
# recoverable -- the node bootstraps from a peer snapshot instead -- so this is
# a tuning knob, not a correctness boundary. Keep it well past the point where
# a peer's own checkpoint would be too stale to donate.
RETENTION_DAYS = 14

# Measured on PG 17.4, not assumed: DROP TABLE <partition> and
# ALTER TABLE ... DETACH PARTITION take exactly the same locks -- ACCESS
# EXCLUSIVE on BOTH the parent and the partition. So this waits for every
# transaction currently touching fpindex_changelog, and while it waits it queues
# new readers behind it.
#
# It is NOT enough that the partition is old and nobody wants its rows: opening
# a partitioned table locks ALL partitions at plan time, before pruning runs, so
# a consumer reading only today's data still holds ACCESS SHARE on a partition
# from a fortnight ago. Adding a `created` predicate does not help; this was
# tested. (Unrelated idle-in-transaction sessions that never touched the table
# do not block it.)
#
# What that means for the feed: a consumer must not hold a transaction open
# across a long-poll wait. Query, end the transaction, wait outside it, query
# again -- then the lock is held for milliseconds and an hourly retry finds a
# gap immediately. Hold it for a 20s poll window and every drop attempt collides.
#
# Hence a short timeout: give up rather than stall the feed, and try again next
# hour. DETACH PARTITION ... CONCURRENTLY would take a weaker lock on the
# parent, but PostgreSQL refuses it outright while a DEFAULT partition exists,
# and the default partition is worth more -- without it a create-ahead job that
# fell behind would fail INSERTs, and those INSERTs are fingerprint submissions.
# Partitions piling up is slow, visible and recoverable; failing submissions is
# an outage.
DROP_LOCK_TIMEOUT = "1s"

_PARTITION_NAME_RE = re.compile(r"^fpindex_changelog_(\d{8})$")


def _partition_name(day: datetime.date) -> str:
    return "fpindex_changelog_" + day.strftime("%Y%m%d")


def _server_today(conn: Connection) -> datetime.date:
    """Use the server's clock, not this process's.

    The partition key is clock_timestamp(), so the only calendar that matters
    is the database's.
    """
    return conn.execute(sql.text("SELECT current_date")).scalar_one()


def _existing_partitions(conn: Connection) -> dict[str, datetime.date]:
    """Dated partitions of the changelog, by name.

    Only names matching the convention are returned, so nothing this job did
    not create can be dropped by it.
    """
    rows = conn.execute(
        sql.text(
            """
            SELECT c.relname
            FROM pg_inherits i
            JOIN pg_class c ON c.oid = i.inhrelid
            JOIN pg_class p ON p.oid = i.inhparent
            WHERE p.relname = :parent
            """
        ),
        {"parent": TABLE_NAME},
    ).scalars()

    partitions = {}
    for name in rows:
        match = _PARTITION_NAME_RE.match(name)
        if match is None:
            continue
        partitions[name] = datetime.datetime.strptime(match.group(1), "%Y%m%d").date()
    return partitions


def create_partitions(conn: Connection, today: datetime.date) -> None:
    for offset in range(CREATE_AHEAD_DAYS + 1):
        day = today + datetime.timedelta(days=offset)
        name = _partition_name(day)
        try:
            conn.execute(
                sql.text(
                    f"CREATE TABLE IF NOT EXISTS {name} "
                    f"PARTITION OF {TABLE_NAME} "
                    f"FOR VALUES FROM (:start) TO (:end)"
                ),
                {"start": day, "end": day + datetime.timedelta(days=1)},
            )
        except SQLAlchemyError:
            # The usual cause is rows for this day sitting in the default
            # partition: PostgreSQL scans it and refuses to create a partition
            # that would have claimed them. They have to be moved by hand.
            logger.exception(
                "Failed to create changelog partition %s; "
                "check whether %s holds rows for that day",
                name,
                DEFAULT_PARTITION,
            )
            return


def drop_partitions(conn: Connection, today: datetime.date) -> None:
    cutoff = today - datetime.timedelta(days=RETENTION_DAYS)
    for name, day in sorted(_existing_partitions(conn).items(), key=lambda kv: kv[1]):
        # The partition covers [day, day + 1), so it is only entirely older
        # than the cutoff once its upper bound has passed it.
        if day + datetime.timedelta(days=1) > cutoff:
            continue
        try:
            conn.execute(sql.text(f"SET lock_timeout = '{DROP_LOCK_TIMEOUT}'"))
            # Dropping the partition detaches it too, so this is one lock
            # acquisition rather than two.
            conn.execute(sql.text(f"DROP TABLE {name}"))
        except SQLAlchemyError:
            # Almost always lock_timeout firing because something else is busy
            # on the table. Harmless: the partition stays attached and readable,
            # and the next run tries again.
            logger.exception("Failed to drop changelog partition %s", name)
            continue
        finally:
            conn.execute(sql.text("SET lock_timeout = DEFAULT"))
        logger.info("Dropped changelog partition %s", name)


def check_default_partition(conn: Connection) -> int:
    """Rows that missed every dated partition. Should always be zero."""
    count = conn.execute(
        sql.text(f"SELECT count(*) FROM ONLY {DEFAULT_PARTITION}")
    ).scalar_one()
    if count:
        logger.error(
            "%s holds %d rows: create-ahead fell behind, and the dated "
            "partitions covering them cannot be created until they are moved",
            DEFAULT_PARTITION,
            count,
        )
    return count


def report_headroom(conn: Connection, today: datetime.date) -> int:
    """Days of partitions in front of us. This is the number to alert on."""
    partitions = _existing_partitions(conn)
    future = [day for day in partitions.values() if day >= today]
    headroom = len(future)
    logger.info("Changelog partition headroom: %d days", headroom)
    return headroom


def run_manage_fpindex_changelog(script: Script) -> None:
    engine = script.db_engines["fingerprint"]
    # Its own autocommit connection rather than the shared session: each DDL
    # statement should commit on its own, so a partition that cannot be dropped
    # right now does not roll back the partitions that were just created, and
    # nothing here holds a transaction open across the whole run.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        today = _server_today(conn)
        create_partitions(conn, today)
        drop_partitions(conn, today)
        check_default_partition(conn)
        report_headroom(conn, today)
