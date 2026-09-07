#!/usr/bin/env python

# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Give a gid to every meta row whose content is unique.

Most of meta predates meta.gid: of 387M rows, 84.5M have no gid and no
duplicate. This fills those in from tmp_meta_gid, a prepared table holding
the recomputed gid for every meta row that existed when it was built.

SCOPE IS SINGLETONS ONLY. The other ~230M gid-less rows are in duplicate
groups, and they cannot all take their computed gid because meta_idx_gid is
unique -- only one row per group can hold it. Collapsing those is the
deduplication's job and a harder problem. The anti-join against tmp_meta_dups
is what confines this to rows that need no merge:

    AND NOT EXISTS (SELECT 1 FROM tmp_meta_dups d WHERE d.gid = g.gid)

WHY THIS IS BATCHED RATHER THAN ONE STATEMENT

meta_idx_gid is UNIQUE on gid WHERE gid IS NOT NULL, and a single violation
aborts the whole statement. That is not hypothetical: 9,351 of the 84.5M
currently collide, so an 84.5M-row UPDATE would abort, throw away hours of
work, and leave the dead rows behind. Batching also keeps each transaction
small enough that standbys can replay it without hitting
max_standby_streaming_delay.

It does NOT let autovacuum reclaim as it goes, which this used to claim. The
default scale factor of 0.2 against meta's ~388M rows puts the trigger near
77.6M dead tuples, and a run of 84.5M only crosses it at the very end:
measured over the real run, autovacuum_count stayed at 0 while the table went
from 68 GB to 95 GB, and vacuum ran once after the job finished. Batching is
justified by transaction size, not by vacuum behaviour.

WHAT COLLIDES, AND WHY SKIPPING IT IS RIGHT

A row that was a singleton when the snapshot was taken may not be one now.
If someone resubmits the same metadata afterwards, find_or_insert_meta looks
the content up by gid, finds nothing -- because our row's gid is still NULL --
and inserts a content-identical row carrying that gid. The old row's computed
gid is then already taken by the new one.

Such a row is no longer a singleton, so leaving its gid NULL is the correct
answer rather than a failure: it is a duplicate, and the deduplication will
merge it into the row that holds the gid. The `report` subcommand counts them;
they stay findable by exactly the query that skipped them, so nothing needs to
be written down as the run goes.

The UPDATE guards against this with a second anti-join rather than catching
the unique violation, because by the time the violation is raised the batch
has already aborted and its work is lost.

WHY tmp_meta_gid CAN BE TRUSTED

It was validated against the 76M rows that already carried a gid -- 76,055,262
compared, 0 mismatched -- so the recomputation agrees with what the server
itself wrote, including for content with quotes, backslashes, non-ASCII and
control characters. Nothing rewrites meta.gid in place either:
find_or_insert_meta sets it on INSERT only, and no other code path updates it.
Together those mean a row's gid today is the gid it had when the snapshot was
built, which is what makes the singleton classification meaningful at all. The
deduplication rests on the same two facts.
"""

import logging
import re

from sqlalchemy import sql

from acoustid.db import FingerprintDB
from acoustid.script import Script

logger = logging.getLogger(__name__)

# Recomputed gid per meta row, and the duplicate groups derived from it. Both
# are prepared out of band and neither is part of the schema.
GID_TABLE = "tmp_meta_gid"
DUPS_TABLE = "tmp_meta_dups"

# One row, holding how far the run has got. Created by `init` and removed by
# `drop`, deliberately not declared in tables.py: meta_gid_backfill_status was
# exactly this table declared alongside real schema, and it outlived its script
# by six years.
PROGRESS_TABLE = "meta_gid_backfill_progress"

# meta ids per batch, not rows updated. Roughly a fifth of the id space needs a
# gid, so this is ~20k updates per transaction.
DEFAULT_BATCH_SIZE = 100000

# meta ids per report window. Large enough that the walk is a handful of
# queries, small enough that each one's probes into meta_pkey stay local.
DEFAULT_REPORT_CHUNK = 60000000

_TABLE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def check_table_name(name: str) -> str:
    if not _TABLE_NAME_RE.match(name):
        raise ValueError("invalid table name: %r" % (name,))
    return name


def init_progress(fingerprint_db: FingerprintDB) -> None:
    fingerprint_db.execute(
        sql.text(
            "CREATE TABLE IF NOT EXISTS {table} ("
            " id integer PRIMARY KEY,"
            " last_meta_id integer NOT NULL,"
            " rows_updated bigint NOT NULL DEFAULT 0,"
            " updated timestamptz NOT NULL DEFAULT now()"
            ")".format(table=PROGRESS_TABLE)
        )
    )
    fingerprint_db.execute(
        sql.text(
            "INSERT INTO {table} (id, last_meta_id) VALUES (1, 0)"
            " ON CONFLICT (id) DO NOTHING".format(table=PROGRESS_TABLE)
        )
    )


def drop_progress(fingerprint_db: FingerprintDB) -> None:
    fingerprint_db.execute(
        sql.text("DROP TABLE IF EXISTS {t}".format(t=PROGRESS_TABLE))
    )


def get_progress(fingerprint_db: FingerprintDB) -> tuple[int, int]:
    """How far the run has got, and how much it has written."""
    row = fingerprint_db.execute(
        sql.text(
            "SELECT last_meta_id, rows_updated FROM {t} WHERE id = 1".format(
                t=PROGRESS_TABLE
            )
        )
    ).first()
    if row is None:
        raise RuntimeError("%s is missing, run init first" % (PROGRESS_TABLE,))
    return row.last_meta_id, row.rows_updated


def last_snapshot_id(fingerprint_db: FingerprintDB, gid_table: str = GID_TABLE) -> int:
    """The highest meta id the snapshot covers.

    Rows above it were created after the snapshot and already have gids of
    their own, so there is nothing here for them.
    """
    return (
        fingerprint_db.execute(
            sql.text("SELECT max(id) FROM {t}".format(t=check_table_name(gid_table)))
        ).scalar()
        or 0
    )


def backfill_batch(
    fingerprint_db: FingerprintDB,
    lo: int,
    hi: int,
    gid_table: str = GID_TABLE,
    dups_table: str = DUPS_TABLE,
) -> int:
    """Fill in one id range and move the cursor. The caller commits.

    The cursor moves in the same transaction as the rows, so resuming is exact
    rather than approximate -- there is no window where the work is committed
    and the record of it is not.
    """
    query = sql.text(
        "UPDATE meta m SET gid = g.gid"
        "  FROM {gid_table} g"
        " WHERE m.id = g.id"
        "   AND m.id >= :lo AND m.id < :hi"
        "   AND m.gid IS NULL"
        # Not a singleton: something else in its group will take the gid.
        "   AND NOT EXISTS (SELECT 1 FROM {dups_table} d WHERE d.gid = g.gid)"
        # No longer a singleton: a row created since the snapshot already holds
        # the gid. Guarding here rather than catching the unique violation,
        # which would only tell us after the batch had already aborted.
        "   AND NOT EXISTS (SELECT 1 FROM meta m2 WHERE m2.gid = g.gid)".format(
            gid_table=check_table_name(gid_table),
            dups_table=check_table_name(dups_table),
        )
    )
    updated = fingerprint_db.execute(query, {"lo": lo, "hi": hi}).rowcount
    fingerprint_db.execute(
        sql.text(
            "UPDATE {t} SET last_meta_id = :hi,"
            " rows_updated = rows_updated + :updated, updated = now()"
            " WHERE id = 1".format(t=PROGRESS_TABLE)
        ),
        {"hi": hi, "updated": updated},
    )
    return updated


def report(
    fingerprint_db: FingerprintDB,
    gid_table: str = GID_TABLE,
    dups_table: str = DUPS_TABLE,
    chunk_size: int = DEFAULT_REPORT_CHUNK,
) -> tuple[int, int]:
    """Singletons still without a gid, and how many are blocked by a collision.

    Walked in id windows rather than as one statement. The cost is not the
    collision check but the join to meta: every singleton surviving the dups
    anti-join is a probe into meta_pkey, ~145.8M of them, and as one statement
    those are random access across a 95 GB table. In windows they become range
    scans with locality. Measured on production: the single-statement form did
    not finish in 45 minutes and was killed twice; six 60M-id windows returned
    the same answer in 18 minutes.

    Note the probe count does not fall as the run progresses -- the m.gid IS
    NULL filter is applied after the probe, so finishing the backfill makes
    this cheaper to summarise but not cheaper to compute.

    Uses the same connection as the rest of the command group rather than a
    read-only one: it takes minutes, which a hot standby would cancel as a
    recovery conflict.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    end = last_snapshot_id(fingerprint_db, gid_table) + 1
    query = sql.text(
        "SELECT count(*) AS remaining,"
        " count(*) FILTER ("
        "   WHERE EXISTS (SELECT 1 FROM meta m2 WHERE m2.gid = g.gid)"
        " ) AS blocked"
        " FROM {gid_table} g JOIN meta m ON m.id = g.id"
        " WHERE g.id >= :lo AND g.id < :hi"
        "   AND m.gid IS NULL"
        "   AND NOT EXISTS (SELECT 1 FROM {dups_table} d WHERE d.gid = g.gid)".format(
            gid_table=check_table_name(gid_table),
            dups_table=check_table_name(dups_table),
        )
    )
    remaining = 0
    blocked = 0
    for lo in range(0, end, chunk_size):
        hi = min(lo + chunk_size, end)
        row = fingerprint_db.execute(query, {"lo": lo, "hi": hi}).one()
        if row.remaining:
            logger.info(
                "%d..%d: %d remaining, %d blocked", lo, hi, row.remaining, row.blocked
            )
        remaining += row.remaining
        blocked += row.blocked
    return remaining, blocked


def run_backfill_singleton_gids(
    script: Script,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
    gid_table: str = GID_TABLE,
    dups_table: str = DUPS_TABLE,
) -> int:
    """Walk the id space from the cursor, filling in gids as it goes."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if script.config.cluster.role != "master":
        logger.info("Not running backfill_singleton_gids in replica mode")
        return 0

    with script.context() as ctx:
        fingerprint_db = ctx.db.get_fingerprint_db()
        lo, already = get_progress(fingerprint_db)
        end = last_snapshot_id(fingerprint_db, gid_table) + 1

    if lo >= end:
        logger.info(
            "Nothing to do, cursor is at %d and the snapshot ends at %d", lo, end
        )
        return 0

    logger.info(
        "Resuming at %d, ending at %d, %d rows written so far", lo, end, already
    )

    total = 0
    batches = 0
    while lo < end:
        if limit is not None and batches >= limit:
            logger.info("Stopping after %d batches, cursor at %d", batches, lo)
            break
        hi = min(lo + batch_size, end)
        with script.context() as ctx:
            updated = backfill_batch(
                ctx.db.get_fingerprint_db(), lo, hi, gid_table, dups_table
            )
            ctx.db.session.commit()
        total += updated
        batches += 1
        lo = hi
        if batches % 100 == 0:
            logger.info("Reached %d, %d rows written this run", lo, total)

    logger.info("Wrote %d rows in %d batches", total, batches)
    return total
