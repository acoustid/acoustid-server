#!/usr/bin/env python

# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Merge each duplicate meta row into the row that holds its gid.

Around 207M of meta's rows are content-identical copies of another row. This
folds each one into the row holding its gid: moves the track_meta rows that
reference it, records where it went, and deletes it.

THE GID CLAIM MADE THIS A PER-ROW OPERATION

This does not know what a duplicate group is, and does not need to. Claiming
the gids first turned "elect a survivor for this group, then merge into it"
into a lookup:

    a row with no gid, whose content gid belongs to some other row,
    is a duplicate of that row

That is the whole rule. The claim already decided who wins, so this walks
meta by id and treats every gid-less row independently. Nothing has to load a
group, hold one together across transactions, or agree with another batch
about who the survivor is.

It is why the 211 groups holding 22.8M members between them need no special
handling. The largest has 685,607 members; they are merged in whatever id
ranges they happen to fall in, in any order, because each resolves to the
same already-decided row. Slicing a group was only ever dangerous when the
survivor was still being chosen.

It also picks up the ~9,545 singletons the gid backfill had to skip, without
knowing they are a special case: their gid is held by a row created after the
snapshot, which is exactly the condition above.

ORDER INSIDE A TRANSACTION

1. record the losers in meta_id_history BEFORE anything deletes them. A crash
   here leaves history for a row that still exists, which the next pass
   corrects. The reverse order leaves a deleted id unresolvable forever.
2. promote track_meta rows whose track has no row for the primary yet
3. fold the rest into the primary's row, summing submission_count
4. delete the losers, guarded so a concurrent reference costs one skipped row
   rather than an aborted batch

Steps 2 and 3 are separate because track_meta_idx_track_id_meta is unique on
(track_id, meta_id): roughly one repoint in five lands on a track that already
references the primary, and a plain UPDATE would trip the index.

WHAT THIS ORPHANS, DELIBERATELY

Folding deletes track_meta rows, and track_meta_source references them by id.
Those references are left dangling. That is safe only because
submission_result has already been reconstructed from track_*_source --
494,462,360 rows, coverage verified exact -- so what those rows recorded now
lives somewhere that does not depend on track_meta ids. Running this before
that reconstruction would have destroyed its input.

WHAT IT DOES NOT RECLAIM

Deleting 207M rows returns the space to the table, not to the filesystem.
meta is 95 GB and will stay 95 GB with a large hole in it. Getting the disk
back needs VACUUM FULL, pg_repack or a dump and restore, which is a separate
decision with a separate cost.
"""

import logging
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import sql

from acoustid.db import FingerprintDB
from acoustid.script import Script

logger = logging.getLogger(__name__)

# The recomputed gid per meta row. Still needed: a gid-less row cannot say
# what its content hashes to without it.
GID_TABLE = "tmp_meta_gid"

# Created by init, removed by drop, and deliberately not declared in
# tables.py -- meta_gid_backfill_status was this kind of table declared
# alongside real schema and outlived its script by six years.
PROGRESS_TABLE = "meta_merge_progress"

# meta ids per transaction. Roughly half the id space is a duplicate, so this
# is ~5000 rows merged and a similar number of track_meta rows touched.
DEFAULT_BATCH_SIZE = 10000

_TABLE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def check_table_name(name: str) -> str:
    if not _TABLE_NAME_RE.match(name):
        raise ValueError("invalid table name: %r" % (name,))
    return name


@dataclass
class Merged:
    """What one batch did."""

    rows: int = 0
    promoted: int = 0
    folded: int = 0
    deferred: int = 0

    def add(self, other: "Merged") -> None:
        self.rows += other.rows
        self.promoted += other.promoted
        self.folded += other.folded
        self.deferred += other.deferred


def init_progress(fingerprint_db: FingerprintDB) -> None:
    fingerprint_db.execute(
        sql.text(
            "CREATE TABLE IF NOT EXISTS {table} ("
            " id integer PRIMARY KEY,"
            " last_meta_id integer NOT NULL,"
            " rows_merged bigint NOT NULL DEFAULT 0,"
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
    row = fingerprint_db.execute(
        sql.text(
            "SELECT last_meta_id, rows_merged FROM {t} WHERE id = 1".format(
                t=PROGRESS_TABLE
            )
        )
    ).first()
    if row is None:
        raise RuntimeError("%s is missing, run init first" % (PROGRESS_TABLE,))
    return row.last_meta_id, row.rows_merged


def last_snapshot_id(fingerprint_db: FingerprintDB, gid_table: str = GID_TABLE) -> int:
    """The highest meta id the snapshot covers.

    Rows above it were created after the snapshot and resolve their own
    duplicates through find_or_insert_meta, so there is nothing here for them.
    """
    return (
        fingerprint_db.execute(
            sql.text("SELECT max(id) FROM {t}".format(t=check_table_name(gid_table)))
        ).scalar()
        or 0
    )


def find_duplicates(
    fingerprint_db: FingerprintDB,
    lo: int,
    hi: int,
    gid_table: str = GID_TABLE,
) -> list[tuple[int, int, uuid.UUID]]:
    """Rows in the range that are duplicates, and what they are duplicates of.

    A row with no gid whose content gid is held by another row is a copy of
    that row. The join to meta on gid is the whole test -- there is no group
    membership to check, because claiming the gid already settled it.
    """
    rows = fingerprint_db.execute(
        sql.text(
            "SELECT m.id AS loser_id, p.id AS primary_id, g.gid AS gid"
            "  FROM {gid_table} g"
            "  JOIN meta m ON m.id = g.id"
            "  JOIN meta p ON p.gid = g.gid"
            " WHERE m.id >= :lo AND m.id < :hi"
            "   AND m.gid IS NULL".format(gid_table=check_table_name(gid_table))
        ),
        {"lo": lo, "hi": hi},
    ).all()
    return [(r.loser_id, r.primary_id, r.gid) for r in rows]


def record_history(
    fingerprint_db: FingerprintDB, pairs: list[tuple[int, int, uuid.UUID]]
) -> None:
    """Where each deleted row went, written before it is deleted.

    meta_id_history plus the unique index on meta.gid is what lets an old
    meta_id still be resolved: old id -> gid -> the row holding it.
    """
    if not pairs:
        return
    fingerprint_db.execute(
        sql.text(
            "INSERT INTO meta_id_history (id, gid)"
            " SELECT * FROM unnest("
            "   CAST(:ids AS integer[]), CAST(:gids AS uuid[])"
            " ) AS t(id, gid)"
            " ON CONFLICT (id) DO NOTHING"
        ),
        {"ids": [p[0] for p in pairs], "gids": [str(p[2]) for p in pairs]},
    )


def repoint_track_meta(
    fingerprint_db: FingerprintDB, pairs: list[tuple[int, int, uuid.UUID]]
) -> tuple[int, int]:
    """Move track_meta off the duplicates and onto the rows they merge into.

    Two statements, because track_meta_idx_track_id_meta is unique on
    (track_id, meta_id) and roughly one repoint in five lands on a track that
    already references the primary. The first promotes, per (track_id,
    primary), the lowest doomed row where the track has no primary row yet;
    after it every affected track has exactly one, so the second folds the
    remainder into it unconditionally.

    Both bump updated, because both change the row: the promote rewrites
    meta_id, the fold changes submission_count. least(created) keeps
    meta.created derivable from min(track_meta.created).
    """
    if not pairs:
        return 0, 0

    params = {
        "loser_ids": [p[0] for p in pairs],
        "primary_ids": [p[1] for p in pairs],
    }
    mapping = (
        "WITH mm AS ("
        "  SELECT * FROM unnest("
        "    CAST(:loser_ids AS integer[]), CAST(:primary_ids AS integer[])"
        "  ) AS t(loser_id, primary_id)"
        ")"
    )

    promoted = fingerprint_db.execute(
        sql.text(
            mapping + ","
            " cand AS ("
            "   SELECT DISTINCT ON (tm.track_id, mm.primary_id)"
            "          tm.id AS id, tm.track_id AS track_id,"
            "          mm.primary_id AS primary_id"
            "     FROM mm JOIN track_meta tm ON tm.meta_id = mm.loser_id"
            "    ORDER BY tm.track_id, mm.primary_id, tm.id"
            " )"
            " UPDATE track_meta t"
            "    SET meta_id = cand.primary_id, updated = now()"
            "   FROM cand"
            "  WHERE t.id = cand.id"
            "    AND NOT EXISTS ("
            "      SELECT 1 FROM track_meta s"
            "       WHERE s.track_id = cand.track_id AND s.meta_id = cand.primary_id"
            "    )"
        ),
        params,
    ).rowcount

    folded = fingerprint_db.execute(
        sql.text(
            mapping + ","
            " doomed AS ("
            "   SELECT tm.id, tm.track_id, tm.submission_count, tm.created,"
            "          mm.primary_id"
            "     FROM mm JOIN track_meta tm ON tm.meta_id = mm.loser_id"
            " ),"
            " agg AS ("
            "   SELECT track_id, primary_id,"
            "          sum(submission_count) AS extra_count,"
            "          min(created) AS min_created,"
            "          array_agg(id) AS doomed_ids"
            "     FROM doomed GROUP BY track_id, primary_id"
            " ),"
            " folded AS ("
            "   UPDATE track_meta t"
            "      SET submission_count = t.submission_count + agg.extra_count,"
            "          created = least(t.created, agg.min_created),"
            "          updated = now()"
            "     FROM agg"
            "    WHERE t.track_id = agg.track_id AND t.meta_id = agg.primary_id"
            "   RETURNING agg.doomed_ids AS doomed_ids"
            " )"
            " DELETE FROM track_meta"
            "  WHERE id IN (SELECT d FROM folded, unnest(folded.doomed_ids) AS d)"
        ),
        params,
    ).rowcount

    return promoted, folded


def delete_duplicates(
    fingerprint_db: FingerprintDB, pairs: list[tuple[int, int, uuid.UUID]]
) -> int:
    """Delete the merged-away rows, skipping any still referenced.

    Guarded rather than relying on the foreign key to fail: a submission
    carrying an explicit meta_id can attach a track_meta row between the
    repoint and here, and one skipped row picked up by a later pass beats
    rolling back the batch.
    """
    if not pairs:
        return 0
    return fingerprint_db.execute(
        sql.text(
            "DELETE FROM meta m"
            " WHERE m.id = ANY(CAST(:ids AS integer[]))"
            "   AND NOT EXISTS (SELECT 1 FROM track_meta tm WHERE tm.meta_id = m.id)"
        ),
        {"ids": [p[0] for p in pairs]},
    ).rowcount


def merge_batch(
    fingerprint_db: FingerprintDB,
    lo: int,
    hi: int,
    gid_table: str = GID_TABLE,
) -> Merged:
    """Merge every duplicate in one id range and move the cursor.

    The caller commits. The cursor moves in the same transaction as the work,
    so resuming is a record of progress rather than an approximation of it.
    """
    result = Merged()
    pairs = find_duplicates(fingerprint_db, lo, hi, gid_table)
    if pairs:
        record_history(fingerprint_db, pairs)
        result.promoted, result.folded = repoint_track_meta(fingerprint_db, pairs)
        result.rows = delete_duplicates(fingerprint_db, pairs)
        result.deferred = len(pairs) - result.rows
        if result.deferred:
            logger.info(
                "%d..%d: %d rows still referenced, left for a later pass",
                lo,
                hi,
                result.deferred,
            )
    fingerprint_db.execute(
        sql.text(
            "UPDATE {t} SET last_meta_id = :hi,"
            " rows_merged = rows_merged + :merged, updated = now()"
            " WHERE id = 1".format(t=PROGRESS_TABLE)
        ),
        {"hi": hi, "merged": result.rows},
    )
    return result


def remaining(
    fingerprint_db: FingerprintDB,
    lo: int,
    hi: int,
    gid_table: str = GID_TABLE,
) -> int:
    """Duplicates still present in an id range.

    Scoped to a range for the same reason the merge is: the join probes
    meta_pkey and meta_idx_gid once per row, and across the whole table those
    are random access over 95 GB.
    """
    return (
        fingerprint_db.execute(
            sql.text(
                "SELECT count(*)"
                "  FROM {gid_table} g"
                "  JOIN meta m ON m.id = g.id"
                "  JOIN meta p ON p.gid = g.gid"
                " WHERE m.id >= :lo AND m.id < :hi"
                "   AND m.gid IS NULL".format(gid_table=check_table_name(gid_table))
            ),
            {"lo": lo, "hi": hi},
        ).scalar()
        or 0
    )


def run_merge(
    script: Script,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
    gid_table: str = GID_TABLE,
) -> Merged:
    """Walk meta by id from the cursor, merging duplicates as it goes."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    total = Merged()
    if script.config.cluster.role != "master":
        logger.info("Not running merge_duplicate_meta in replica mode")
        return total

    with script.context() as ctx:
        fingerprint_db = ctx.db.get_fingerprint_db()
        lo, already = get_progress(fingerprint_db)
        end = last_snapshot_id(fingerprint_db, gid_table) + 1

    if lo >= end:
        logger.info(
            "Nothing to do, cursor is at %d and the snapshot ends at %d", lo, end
        )
        return total

    logger.info("Resuming at %d, ending at %d, %d rows merged so far", lo, end, already)

    batches = 0
    while lo < end and (limit is None or batches < limit):
        hi = min(lo + batch_size, end)
        with script.context() as ctx:
            total.add(merge_batch(ctx.db.get_fingerprint_db(), lo, hi, gid_table))
            ctx.db.session.commit()
        batches += 1
        lo = hi
        if batches % 100 == 0:
            logger.info(
                "Reached %d: %d rows merged, %d track_meta repointed, %d folded",
                lo,
                total.rows,
                total.promoted,
                total.folded,
            )

    logger.info(
        "Merged %d rows in %d batches: %d track_meta repointed, %d folded, %d deferred",
        total.rows,
        batches,
        total.promoted,
        total.folded,
        total.deferred,
    )
    return total
