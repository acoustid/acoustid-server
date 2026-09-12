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

The guard is a snapshot test, so it can still lose: a row committed between
the DELETE's snapshot and the end-of-statement foreign key check raises
instead of being skipped. That is the same event with a louder failure mode,
so it is handled the same way -- the batch rolls back, the range is recorded,
and the walk carries on. A multi-day run does not end because one submission
arrived at an unlucky moment.

A guarded skip is not the end of the story. The range is recorded in
meta_merge_deferred and swept again once the forward walk is done, because a
reference that appeared mid-batch is gone by the time the repoint runs again.
Ranges that still defer stay in the table, so "did this finish?" is a query
rather than a guess: the run does not report itself complete while it holds
rows it never merged.

Steps 2 and 3 are separate because track_meta_idx_uniq is unique on
(track_id, meta_id): roughly nine repoints in ten land on a track that already
references the primary, and a plain UPDATE would trip the index. Step 3 is
therefore the hot one, which is worth knowing before optimising step 2.

WHAT IT CHECKS BEFORE DELETING

The gid table is prepared out of band and selectable with --gid-table, and a
wrong entry sends a row's track_meta into an unrelated meta row and then
deletes the evidence. Both rows are already joined, so the merge compares the
seven columns the gid is derived from and leaves any pair that disagrees
alone, loudly. It costs nothing and makes 207M irreversible deletes
self-checking rather than trusting a table that is not in the schema.

The comparison uses the same falsy-is-absent rule as generate_meta_gid, which
skips empty strings and zeros when it hashes: a row storing '' and a row
storing NULL hash alike and must compare alike, or the check would reject the
very pairs it exists to confirm.

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
from sqlalchemy.exc import IntegrityError

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

# Ranges the delete guard skipped, waiting for another sweep. Same lifetime as
# PROGRESS_TABLE and dropped with it.
DEFERRED_TABLE = "meta_merge_deferred"

# The columns generate_meta_gid hashes, with the value that counts as absent.
# It skips anything falsy, so '' and NULL are one value and so are 0 and NULL;
# comparing them strictly would reject rows that really do hash alike.
CONTENT_COLUMNS = (
    ("track", "''"),
    ("artist", "''"),
    ("album", "''"),
    ("album_artist", "''"),
    ("track_no", "0"),
    ("disc_no", "0"),
    ("year", "0"),
)

SAME_CONTENT = " AND ".join(
    "nullif(m.{c}, {a}) IS NOT DISTINCT FROM nullif(p.{c}, {a})".format(c=c, a=a)
    for c, a in CONTENT_COLUMNS
)

# meta ids per transaction. Roughly half the id space is a duplicate, so this
# is ~5000 rows merged and a similar number of track_meta rows touched.
DEFAULT_BATCH_SIZE = 10000

# meta ids per counting window. Bigger than a batch because nothing is
# written, small enough that each window still probes an index rather than
# walking 95 GB.
DEFAULT_CHUNK_SIZE = 60000000

_TABLE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def check_table_name(name: str) -> str:
    if not _TABLE_NAME_RE.match(name):
        raise ValueError("invalid table name: %r" % (name,))
    return name


@dataclass
class Report:
    """What is left, in the shape report prints it.

    Windows with nothing in them are dropped on the way out, so a run that is
    nearly finished prints a handful of lines rather than several hundred.
    """

    windows: list[tuple[int, int, int]]
    total: int
    deferred: list[tuple[int, int]]


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
    # Added after the first version of this script, so a progress table left
    # by an earlier init gains the column instead of missing it.
    fingerprint_db.execute(
        sql.text(
            "ALTER TABLE {table} ADD COLUMN IF NOT EXISTS"
            " rows_deferred bigint NOT NULL DEFAULT 0".format(table=PROGRESS_TABLE)
        )
    )
    fingerprint_db.execute(
        sql.text(
            "CREATE TABLE IF NOT EXISTS {table} ("
            " lo integer PRIMARY KEY,"
            " hi integer NOT NULL,"
            " rows integer NOT NULL,"
            " updated timestamptz NOT NULL DEFAULT now()"
            ")".format(table=DEFERRED_TABLE)
        )
    )


def drop_progress(fingerprint_db: FingerprintDB) -> None:
    fingerprint_db.execute(
        sql.text("DROP TABLE IF EXISTS {t}".format(t=DEFERRED_TABLE))
    )
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


def record_deferred(fingerprint_db: FingerprintDB, lo: int, hi: int, rows: int) -> None:
    """Remember a range the delete guard skipped, so a later sweep finds it."""
    fingerprint_db.execute(
        sql.text(
            "INSERT INTO {t} (lo, hi, rows) VALUES (:lo, :hi, :rows)"
            " ON CONFLICT (lo) DO UPDATE"
            " SET hi = excluded.hi, rows = excluded.rows,"
            "     updated = now()".format(t=DEFERRED_TABLE)
        ),
        {"lo": lo, "hi": hi, "rows": rows},
    )


def clear_deferred(fingerprint_db: FingerprintDB, lo: int) -> None:
    """Forget a range that a later sweep finished."""
    fingerprint_db.execute(
        sql.text("DELETE FROM {t} WHERE lo = :lo".format(t=DEFERRED_TABLE)),
        {"lo": lo},
    )


def get_deferred(fingerprint_db: FingerprintDB) -> list[tuple[int, int]]:
    """The ranges the delete guard skipped, lowest first.

    Empty when the table is not there. report answered without a progress
    table before this one existed, and asking what was deferred by a run that
    never started is a fair question with a boring answer.
    """
    exists = fingerprint_db.execute(
        sql.text("SELECT to_regclass(:t) IS NOT NULL"), {"t": DEFERRED_TABLE}
    ).scalar()
    if not exists:
        return []
    rows = fingerprint_db.execute(
        sql.text("SELECT lo, hi FROM {t} ORDER BY lo".format(t=DEFERRED_TABLE))
    ).all()
    return [(r.lo, r.hi) for r in rows]


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

    The gid comes from a table this script does not own, so the content is
    compared before the pair is handed on to be deleted. A disagreement means
    the gid table is wrong about this row; it is reported and the row is left
    exactly as it is, which is recoverable, unlike merging it.
    """
    rows = fingerprint_db.execute(
        sql.text(
            "SELECT m.id AS loser_id, p.id AS primary_id, g.gid AS gid,"
            "       ({same_content}) AS same_content"
            "  FROM {gid_table} g"
            "  JOIN meta m ON m.id = g.id"
            "  JOIN meta p ON p.gid = g.gid"
            " WHERE m.id >= :lo AND m.id < :hi"
            "   AND m.gid IS NULL".format(
                gid_table=check_table_name(gid_table), same_content=SAME_CONTENT
            )
        ),
        {"lo": lo, "hi": hi},
    ).all()
    mismatched = [r.loser_id for r in rows if not r.same_content]
    if mismatched:
        logger.warning(
            "%d..%d: %d rows whose gid points at different content, left alone: %s",
            lo,
            hi,
            len(mismatched),
            ", ".join(str(i) for i in mismatched[:20]),
        )
    return [(r.loser_id, r.primary_id, r.gid) for r in rows if r.same_content]


def record_history(
    fingerprint_db: FingerprintDB, pairs: list[tuple[int, int, uuid.UUID]]
) -> None:
    """Where each deleted row went, written before it is deleted.

    meta_id_history plus the unique index on meta.gid is what lets an old
    meta_id still be resolved: old id -> gid -> the row holding it.

    Nothing in this codebase performs that lookup yet -- the table has been
    written since 2020 and never read -- so this keeps the resolution possible
    rather than making it available. A caller that needs it still has to join
    meta_id_history to meta itself.
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

    Two statements, because track_meta_idx_uniq is unique on
    (track_id, meta_id) and most repoints land on a track that already
    references the primary. The first promotes, per (track_id, primary), the
    lowest doomed row where the track has no primary row yet; after it every
    affected track has exactly one, so the second folds the remainder into it
    unconditionally.

    The fold is the common path by a wide margin. Over the 204,432,306 rows
    the production run merged, 14,656,185 were promoted and the remaining
    92.8% folded. Per id band the promote rate runs from 1.6% to 10.7% with
    no trend as the walk proceeds: the 310-328M tail is 6.07% against 7.31%
    for the 265M ids beneath it, and the two bands below 2.2% are the two
    smallest, together 1.3% of everything merged. The ratio is a property of
    the data, not of how far the cursor has travelled. An earlier version of
    this docstring guessed one in five and had it backwards; the numbers are
    the script's own counters, so they are worth about as much as the
    rowcounts they come from, but not by a factor of four.

    Both bump updated, because both change the row: the promote rewrites
    meta_id, the fold changes submission_count. least(created) keeps
    meta.created derivable from min(track_meta.created).

    WHY BOTH STATEMENTS SAY "meta_id + 0"

    It defeats an index on purpose, and taking it out costs about 90 seconds
    per batch. Both statements have to find a track's row for a given meta
    row, there are two indexes that can do it, and the planner picks the
    wrong one:

        Index Scan using track_meta_idx_meta_id
          Index Cond: (meta_id = agg.primary_id)
          Filter:     (track_id = agg.track_id)

    Both quals are indexable, both paths estimate one row at the same cost,
    and it takes meta_id. The estimate is right about the result and wrong
    about the work. The primary here is a merge survivor, and survivors are
    the most heavily referenced meta rows there are -- up to 639,492
    track_meta rows for a single one -- so every entry is read and every row
    heap-fetched to keep the one whose track_id matches. Measured on
    production over 6,991 pairs: 84,148,065 buffer hits, 93.7 seconds, no IO
    wait. Pure spinning.

    Statistics cannot reach this. The primary id arrives as a runtime join
    variable, so the MCV list that does know these ids are outliers is never
    consulted and the planner uses the average, which is 1.1.

    track_id has no such skew: 1.114 rows per track_id over a 0.5% sample,
    78 at worst, and 10 at worst across the tracks a batch actually touches.
    So the cheap direction is to probe by track_id and filter meta_id, and
    the planner will never choose it while meta_id is sitting there as an
    Index Cond. Adding 0 makes the column side non-indexable, which leaves
    track_id as the only indexable qual and track_meta_idx_uniq as the only
    index with track_id in front:

        Index Scan using track_meta_idx_track_id_meta
          Index Cond: (track_id = agg.track_id)
          Filter:     (agg.primary_id = (meta_id + 0))

    633,833 buffers against 84,148,065, and 13.8 seconds against 93.7, most
    of what is left being physical reads of a cold index rather than CPU.
    (Production calls the composite index track_meta_idx_track_id_meta; it
    is the same index this file declares as track_meta_idx_uniq.)

    The point is not that this is cheaper. It is that the wrong index cannot
    be used at all, so no future drift in the statistics can bring the 90
    seconds back.

    One side effect, so it is not mistaken later for a bug: the planner
    cannot estimate selectivity for "meta_id + 0 = X" and falls back to a
    default, so the fold's Update node reports rows=44 against an actual
    ~6,500 and the DELETE above it inherits the same error. That misestimate
    is the opacity doing its job, not a symptom. It does not reach the plan
    shape, because everything downstream runs off the CTE's real output. An earlier attempt at this moved the lookup into a
    MATERIALIZED CTE and updated by primary key, on the theory that the
    planner would prefer the composite index if asked in isolation. It does
    not; that only relocated the same scan into the CTE.

    Do not validate this with a SELECT. A standalone
    "SELECT 1 ... WHERE track_id = ? AND meta_id = ?" goes index-only with
    both columns as Index Cond, which is already optimal and which + 0 makes
    six times worse. The promote's NOT EXISTS does not get that plan inside
    the UPDATE it belongs to, and needs the + 0 like the fold does. A
    SELECT-shaped probe has given the wrong answer about this statement
    twice now, in both directions. Plan the statement that ships.
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
            # + 0 is deliberate and load-bearing. See WHY BOTH STATEMENTS SAY
            # "meta_id + 0" above before removing it.
            "       WHERE s.track_id = cand.track_id"
            "         AND s.meta_id + 0 = cand.primary_id"
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
            # + 0 is deliberate and load-bearing. See WHY BOTH STATEMENTS SAY
            # "meta_id + 0" above before removing it.
            "    WHERE t.track_id = agg.track_id"
            "      AND t.meta_id + 0 = agg.primary_id"
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


def bump_progress(
    fingerprint_db: FingerprintDB, hi: int, merged: int, deferred: int
) -> None:
    """Move the cursor to hi and add to the counters.

    greatest(), because a deferred sweep re-runs ranges behind the cursor and
    must not drag it back over work that is finished.
    """
    fingerprint_db.execute(
        sql.text(
            "UPDATE {t} SET last_meta_id = greatest(last_meta_id, :hi),"
            " rows_merged = rows_merged + :merged,"
            " rows_deferred = rows_deferred + :deferred, updated = now()"
            " WHERE id = 1".format(t=PROGRESS_TABLE)
        ),
        {"hi": hi, "merged": merged, "deferred": deferred},
    )


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
            "%d..%d: %d rows still referenced, recorded for another sweep",
            lo,
            hi,
            result.deferred,
        )
        record_deferred(fingerprint_db, lo, hi, result.deferred)
    else:
        # Nothing left here, so a range recorded by an earlier sweep is done.
        clear_deferred(fingerprint_db, lo)
    bump_progress(fingerprint_db, hi, result.rows, result.deferred)
    return result


def run_batch(script: Script, lo: int, hi: int, gid_table: str, total: Merged) -> None:
    """One batch and its commit, treating a lost race as a deferral.

    The foreign key can fire on a row that the guard's snapshot could not see.
    Nothing is lost when it does -- the batch rolls back whole -- so the range
    is recorded and the cursor moves on, exactly as for a guarded skip.
    """
    try:
        with script.context() as ctx:
            batch = merge_batch(ctx.db.get_fingerprint_db(), lo, hi, gid_table)
            ctx.db.session.commit()
        # After the commit: an abort throws the batch away, and counting work
        # the database rolled back would overstate every total in the summary.
        total.add(batch)
    except IntegrityError:
        logger.warning(
            "%d..%d: a reference arrived mid-delete and aborted the batch,"
            " recorded for another sweep",
            lo,
            hi,
        )
        with script.context() as ctx:
            fingerprint_db = ctx.db.get_fingerprint_db()
            record_deferred(fingerprint_db, lo, hi, 0)
            bump_progress(fingerprint_db, hi, 0, 0)
            ctx.db.session.commit()


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


def report_duplicates(
    fingerprint_db: FingerprintDB,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    gid_table: str = GID_TABLE,
) -> Report:
    """Everything report needs: what is left, and what was put off.

    Counted in windows for the same reason the merge runs in batches -- the
    join probes two indexes per row and the whole table at once is random
    access over 95 GB.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    end = last_snapshot_id(fingerprint_db, gid_table) + 1
    windows = []
    total = 0
    for lo in range(0, end, chunk_size):
        hi = min(lo + chunk_size, end)
        found = remaining(fingerprint_db, lo, hi, gid_table)
        if found:
            windows.append((lo, hi, found))
        total += found
    return Report(windows=windows, total=total, deferred=get_deferred(fingerprint_db))


def run_merge(
    script: Script,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
    gid_table: str = GID_TABLE,
) -> Merged:
    """Walk meta by id from the cursor, then sweep whatever the guard skipped.

    The walk moves the cursor; the sweep does not. A range the guard skipped
    is revisited in the same run, and if it skips again it stays recorded, so
    a finished run and a run with work left over do not look the same.
    """
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
        pending = get_deferred(fingerprint_db)

    if lo >= end and not pending:
        logger.info(
            "Nothing to do, cursor is at %d and the snapshot ends at %d", lo, end
        )
        return total

    if lo < end:
        logger.info(
            "Resuming at %d, ending at %d, %d rows merged so far", lo, end, already
        )
    else:
        logger.info("Cursor is at the end, sweeping %d deferred ranges", len(pending))

    batches = 0
    while lo < end and (limit is None or batches < limit):
        hi = min(lo + batch_size, end)
        run_batch(script, lo, hi, gid_table, total)
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

    # Read again: the walk records ranges of its own as it goes.
    with script.context() as ctx:
        pending = get_deferred(ctx.db.get_fingerprint_db())

    for d_lo, d_hi in pending:
        if limit is not None and batches >= limit:
            break
        run_batch(script, d_lo, d_hi, gid_table, total)
        batches += 1

    with script.context() as ctx:
        left = get_deferred(ctx.db.get_fingerprint_db())

    logger.info(
        "Merged %d rows in %d batches: %d track_meta repointed, %d folded, %d deferred",
        total.rows,
        batches,
        total.promoted,
        total.folded,
        total.deferred,
    )
    if left:
        logger.warning(
            "%d ranges still hold rows the guard skipped, run again to sweep them: %s",
            len(left),
            ", ".join("%d..%d" % r for r in left[:10]),
        )
    return total
