#!/usr/bin/env python

# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Reconstruct submission_result rows for submissions that predate the table.

submission_result was added in 2019 and its first row is submission 502439339.
Everything submitted before that has no result row, and the submissions
themselves are gone -- `submission` is purged by partition and now starts at
860,000,000. What survives is the *_source tables, which are never purged and
reach back to submission_id 1, so they are the only remaining record of what
those submissions carried.

Reconstruction drives off fingerprint_source: every import writes one, it
covers the whole history, and it supplies fingerprint_id and source_id
directly. That also excludes, without any special case, the ~9,920
submissions that have metadata but no fingerprint_source row -- they cannot
be reconstructed at all, because fingerprint_id is NOT NULL and nothing
records which fingerprint they carried. Do not "fix" this by unioning in the
other source tables; it would reintroduce rows that cannot be completed.

Two things about reconstructed rows differ from natively written ones, both
unavoidable:

  created     is when the import ran, not when the user submitted. The
              submission rows holding the true time are gone. So there is a
              silent discontinuity at submission 502439339 that will look
              like corruption to anyone who does not know about it.
  handled_at  is always NULL. Nothing anywhere retains it, and an honest gap
              beats a plausible invention.

Where a submission has more than one fingerprint_source row (0.116% of them,
and 85% of those are the same fingerprint recorded twice) the lowest
fingerprint_id wins. That is a deterministic choice, not a reconstruction of
what the import actually did: the live path took the highest-scoring index
match above FINGERPRINT_MERGE_THRESHOLD, and that score is not recorded
anywhere. No available rule reproduces it, so --validate reports how often
this one disagrees rather than pretending to find the real one.

One column is beyond validation's reach. No native submission_result row has
ever had a non-null foreignid, and all 43,189 track_foreignid_source rows sit
below the watershed -- so --validate reconstructs NULL for that column on
every row it compares, matches NULL against NULL, and reports the mapping
correct without ever exercising it. Below the watershed those 43,189 rows are
the only ones the script writes a foreignid for, in a column where no native
row has one. The format is what import_submission would have written, but
that is read off the code rather than observed in data, and it is the one
part of the mapping the diff cannot check.

Run --validate before --run. It reconstructs the range above the watershed,
where native rows already exist, and diffs against them -- 372M rows of
ground truth at no write risk.

The run itself is recoverable. Ranges are claimed in ascending id order and
`init` queues up to the watershed by default, so every row written is one
that had no native row -- which makes

    DELETE FROM submission_result WHERE submission_id < <watershed>

an exact undo: it removes everything the backfill wrote and cannot touch a
natively written row. That holds only while the queue stays below the
watershed. Queueing past it, to fill the gaps up there, mixes reconstructed
rows in among native ones and gives up the clean delete.

--max-ranges stops after a set number of ranges, between ranges rather than
mid-range, so a first pass can write one range and leave the rest pending
while you look at what it did.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Iterator, Sequence

from sqlalchemy import sql

from acoustid.db import AppDB, FingerprintDB, IngestDB
from acoustid.script import Script, ScriptContext

logger = logging.getLogger(__name__)

PROGRESS_TABLE = "submission_result_backfill_progress"

# Holds a recomputed gid for every meta row that existed when it was built.
# Load-bearing: most meta rows still have no gid of their own. The fallback
# has no hole, because rows created after the snapshot always have a gid --
# find_or_insert_meta sets one -- but that only holds while the deduplication
# has not run yet, since it deletes meta rows.
GID_TABLE = "tmp_meta_gid"

# gid_table is the one table name that comes from a command-line option rather
# than a constant, and it is interpolated into a FROM clause.  Anyone who can
# pass it can already run `manage.py shell`, so this is not a privilege
# boundary -- it just turns a typo into a clear error instead of a confusing
# SQL one.
_TABLE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

DEFAULT_BATCH_SIZE = 10000
DEFAULT_RANGE_SIZE = 1000000

# Columns compared strictly by --validate. created and handled_at are left out
# on purpose: reconstructed created is import time against the native rows'
# submit time, so it differs for every row by construction, and handled_at is
# always NULL. Including them would report a 100% failure rate and bury the
# real signal.
COMPARED_COLUMNS = (
    "account_id",
    "application_id",
    "application_version",
    "fingerprint_id",
    "track_id",
    "meta_gid",
    "mbid",
    "puid",
    "foreignid",
)


def check_table_name(name: str) -> str:
    if not _TABLE_NAME_RE.match(name):
        raise ValueError("invalid table name: %r" % (name,))
    return name


@dataclass
class Row:
    """One reconstructed submission_result row."""

    submission_id: int
    created: datetime
    account_id: int
    application_id: int
    application_version: str | None
    fingerprint_id: int
    track_id: int
    meta_gid: uuid.UUID | None
    mbid: uuid.UUID | None
    puid: uuid.UUID | None
    foreignid: str | None

    def values(self) -> dict[str, Any]:
        return {
            "submission_id": self.submission_id,
            "created": self.created,
            "account_id": self.account_id,
            "application_id": self.application_id,
            "application_version": self.application_version,
            "fingerprint_id": self.fingerprint_id,
            "track_id": self.track_id,
            "meta_gid": self.meta_gid,
            "mbid": self.mbid,
            "puid": self.puid,
            "foreignid": self.foreignid,
        }


@dataclass
class Skipped:
    """Submissions that could not be completed, by reason.

    no_fingerprint means fingerprint_source named a fingerprint row that does
    not exist -- a dangling reference, not a fingerprint without a track.
    fingerprint.track_id is NOT NULL, so the track is never the missing part.
    """

    no_fingerprint: int = 0
    no_source: int = 0

    def total(self) -> int:
        return self.no_fingerprint + self.no_source


def _pick(
    db: IngestDB, table: str, column: str, submission_ids: Sequence[int]
) -> dict[int, int]:
    """One row per submission from a *_source table, lowest id wins.

    The same arbitrary-but-deterministic choice the driver makes for
    fingerprint_source, and it affects real rows: at least 16,507 submissions
    have more than one track_meta_source row.  Nothing records which one the
    import actually used, so there is no better rule available -- only a
    consistent one.
    """
    query = sql.text(
        "SELECT DISTINCT ON (submission_id) submission_id, {column}"
        " FROM {table} WHERE submission_id = ANY(CAST(:ids AS integer[]))"
        " ORDER BY submission_id, {column}".format(table=table, column=column)
    )
    return {
        row.submission_id: getattr(row, column)
        for row in db.execute(query, {"ids": list(submission_ids)})
    }


def _lookup(
    db: Any, table: str, key: str, value: str, ids: Iterable[int]
) -> dict[int, Any]:
    ids = sorted(set(i for i in ids if i is not None))
    if not ids:
        return {}
    query = sql.text(
        "SELECT {key}, {value} FROM {table}"
        " WHERE {key} = ANY(CAST(:ids AS integer[]))".format(
            table=table, key=key, value=value
        )
    )
    return {getattr(r, key): getattr(r, value) for r in db.execute(query, {"ids": ids})}


def lookup_meta_gids(
    fingerprint_db: FingerprintDB, meta_ids: Iterable[int], gid_table: str = GID_TABLE
) -> dict[int, uuid.UUID | None]:
    """meta.gid, falling back to the recomputed snapshot where it is not set."""
    ids = sorted(set(i for i in meta_ids if i is not None))
    if not ids:
        return {}
    query = sql.text(
        "SELECT m.id, COALESCE(m.gid, t.gid) AS gid"
        " FROM meta m LEFT JOIN {gid_table} t ON t.id = m.id"
        " WHERE m.id = ANY(CAST(:ids AS integer[]))".format(
            gid_table=check_table_name(gid_table)
        )
    )
    return {r.id: r.gid for r in fingerprint_db.execute(query, {"ids": ids})}


def lookup_foreignids(
    fingerprint_db: FingerprintDB, foreignid_ids: Iterable[int]
) -> dict[int, str]:
    """foreignid_id -> "vendor:name".

    The format comes from get_foreignid in data/foreignid.py, which is what
    import_submission assigns to submission_result.foreignid -- so this is
    what the live path would write.  It has never actually written one: no
    native row in submission_result has a non-null foreignid, because all
    43,189 track_foreignid_source rows sit below the watershed.  See the
    module docstring; validate cannot reach this column.
    """
    ids = sorted(set(i for i in foreignid_ids if i is not None))
    if not ids:
        return {}
    query = sql.text(
        "SELECT f.id, v.name || ':' || f.name AS name"
        " FROM foreignid f JOIN foreignid_vendor v ON v.id = f.vendor_id"
        " WHERE f.id = ANY(CAST(:ids AS integer[]))"
    )
    return {r.id: r.name for r in fingerprint_db.execute(query, {"ids": ids})}


def lookup_sources(
    app_db: AppDB, source_ids: Iterable[int], cache: dict[int, Any]
) -> dict[int, Any]:
    """source_id -> (account_id, application_id, version), cached in process.

    source_id repeats heavily -- one row per (account, application, version) --
    so a plain dict pays for itself quickly.  Clearing wholesale rather than
    evicting is crude and would thrash if a range's working set exceeded the
    cap, but with that much repetition a range sees far fewer distinct sources
    than the cap, so the simple version costs nothing in practice.
    """
    if len(cache) > 200000:
        cache.clear()
    missing = sorted({i for i in source_ids if i is not None and i not in cache})
    if missing:
        query = sql.text(
            "SELECT id, account_id, application_id, version FROM source"
            " WHERE id = ANY(CAST(:ids AS integer[]))"
        )
        for row in app_db.execute(query, {"ids": missing}):
            cache[row.id] = row
    return cache


def _chain(link: dict[int, int], target: dict[int, Any], submission_id: int) -> Any:
    """submission -> *_source id -> the value it points at, or None."""
    source_id = link.get(submission_id)
    return target.get(source_id) if source_id is not None else None


def build_rows(
    ingest_db: IngestDB,
    fingerprint_db: FingerprintDB,
    app_db: AppDB,
    submission_ids: Sequence[int],
    source_cache: dict[int, Any] | None = None,
    gid_table: str = GID_TABLE,
) -> tuple[list[Row], Skipped]:
    """Reconstruct submission_result rows for a batch of submission ids."""
    skipped = Skipped()
    if not submission_ids:
        return [], skipped

    ids = list(submission_ids)

    # The driver.  DISTINCT ON keeps source_id and created coherent with the
    # fingerprint_id they came from, rather than taking min() of each column
    # independently and mixing two rows together.
    driver = sql.text(
        "SELECT DISTINCT ON (submission_id)"
        "       submission_id, fingerprint_id, source_id, created"
        "  FROM fingerprint_source"
        " WHERE submission_id = ANY(CAST(:ids AS integer[]))"
        " ORDER BY submission_id, fingerprint_id"
    )
    base = {r.submission_id: r for r in ingest_db.execute(driver, {"ids": ids})}
    if not base:
        return [], skipped

    present = sorted(base)
    track_meta = _pick(ingest_db, "track_meta_source", "track_meta_id", present)
    track_mbid = _pick(ingest_db, "track_mbid_source", "track_mbid_id", present)
    track_puid = _pick(ingest_db, "track_puid_source", "track_puid_id", present)
    track_foreignid = _pick(
        ingest_db, "track_foreignid_source", "track_foreignid_id", present
    )

    tracks = _lookup(
        fingerprint_db,
        "fingerprint",
        "id",
        "track_id",
        (r.fingerprint_id for r in base.values()),
    )
    meta_ids = _lookup(
        fingerprint_db, "track_meta", "id", "meta_id", track_meta.values()
    )
    mbids = _lookup(fingerprint_db, "track_mbid", "id", "mbid", track_mbid.values())
    puids = _lookup(fingerprint_db, "track_puid", "id", "puid", track_puid.values())
    foreignid_ids = _lookup(
        fingerprint_db,
        "track_foreignid",
        "id",
        "foreignid_id",
        track_foreignid.values(),
    )
    gids = lookup_meta_gids(fingerprint_db, meta_ids.values(), gid_table)
    foreignids = lookup_foreignids(fingerprint_db, foreignid_ids.values())

    if source_cache is None:
        source_cache = {}
    sources = lookup_sources(app_db, (r.source_id for r in base.values()), source_cache)

    rows = []
    for submission_id in present:
        row = base[submission_id]
        track_id = tracks.get(row.fingerprint_id)
        if track_id is None:
            skipped.no_fingerprint += 1
            continue
        source = sources.get(row.source_id)
        if source is None:
            skipped.no_source += 1
            continue

        meta_id = _chain(track_meta, meta_ids, submission_id)
        foreignid_id = _chain(track_foreignid, foreignid_ids, submission_id)
        rows.append(
            Row(
                submission_id=submission_id,
                created=row.created,
                account_id=source.account_id,
                application_id=source.application_id,
                application_version=source.version,
                fingerprint_id=row.fingerprint_id,
                track_id=track_id,
                meta_gid=gids.get(meta_id) if meta_id is not None else None,
                mbid=_chain(track_mbid, mbids, submission_id),
                puid=_chain(track_puid, puids, submission_id),
                foreignid=foreignids.get(foreignid_id) if foreignid_id else None,
            )
        )
    return rows, skipped


def insert_rows(ingest_db: IngestDB, rows: Sequence[Row]) -> int:
    """Write reconstructed rows, leaving any that already exist alone.

    ON CONFLICT DO NOTHING makes a re-run of a partly-finished range free, and
    lets the same code fill the gaps above the watershed without a special
    case for them.
    """
    if not rows:
        return 0
    query = sql.text(
        "INSERT INTO submission_result"
        " (submission_id, created, account_id, application_id, application_version,"
        "  fingerprint_id, track_id, meta_gid, mbid, puid, foreignid)"
        " VALUES (:submission_id, :created, :account_id, :application_id,"
        "         :application_version, :fingerprint_id, :track_id,"
        "         CAST(:meta_gid AS uuid), CAST(:mbid AS uuid),"
        "         CAST(:puid AS uuid), :foreignid)"
        " ON CONFLICT (submission_id) DO NOTHING"
    )
    params = []
    for row in rows:
        values = row.values()
        for key in ("meta_gid", "mbid", "puid"):
            if values[key] is not None:
                values[key] = str(values[key])
        params.append(values)
    return ingest_db.execute(query, params).rowcount


# --- work queue -------------------------------------------------------------
#
# Deliberately not declared in tables.py.  It is scaffolding for a one-off job,
# and the last table of this kind that was declared alongside real schema --
# meta_gid_backfill_status -- outlived its script by six years because nothing
# distinguished it.  Created by --init, removed by --drop.


def init_queue(
    ingest_db: IngestDB, lo: int, hi: int, range_size: int = DEFAULT_RANGE_SIZE
) -> int:
    if range_size < 1:
        raise ValueError("range_size must be positive")
    ingest_db.execute(
        sql.text(
            "CREATE TABLE IF NOT EXISTS {table} ("
            " lo bigint PRIMARY KEY,"
            " hi bigint NOT NULL,"
            " state text NOT NULL DEFAULT 'pending',"
            " claimed_by text,"
            " claimed_at timestamptz,"
            " rows_written bigint,"
            " rows_skipped bigint,"
            " finished_at timestamptz"
            ")".format(table=PROGRESS_TABLE)
        )
    )
    ranges = [
        (start, min(start + range_size, hi)) for start in range(lo, hi, range_size)
    ]
    if not ranges:
        return 0
    # Only the ranges that were not already queued, so re-running init on a
    # partly-finished queue reports what it added rather than what it saw.
    result = ingest_db.execute(
        sql.text(
            "INSERT INTO {table} (lo, hi) VALUES (:lo, :hi)"
            " ON CONFLICT (lo) DO NOTHING".format(table=PROGRESS_TABLE)
        ),
        [{"lo": lo, "hi": hi} for lo, hi in ranges],
    )
    return result.rowcount


def drop_queue(ingest_db: IngestDB) -> None:
    ingest_db.execute(sql.text("DROP TABLE IF EXISTS {t}".format(t=PROGRESS_TABLE)))


def claim_range(ingest_db: IngestDB, worker: str) -> tuple[int, int] | None:
    """Take the next pending range, lowest first.

    Ascending order is deliberate: the oldest submissions are the ones safely
    below the watershed, so a run that goes wrong early has only written rows
    that no native row occupies.

    SKIP LOCKED so workers never queue behind each other; a fast range frees
    its worker immediately rather than waiting for a slow neighbour.
    """
    query = sql.text(
        "UPDATE {table} SET state='running', claimed_by=:worker, claimed_at=now()"
        " WHERE lo = (SELECT lo FROM {table} WHERE state='pending'"
        "             ORDER BY lo LIMIT 1 FOR UPDATE SKIP LOCKED)"
        " RETURNING lo, hi".format(table=PROGRESS_TABLE)
    )
    row = ingest_db.execute(query, {"worker": worker}).first()
    return (row.lo, row.hi) if row is not None else None


def finish_range(
    ingest_db: IngestDB, lo: int, written: int, skipped: int, state: str = "done"
) -> None:
    ingest_db.execute(
        sql.text(
            "UPDATE {table} SET state=:state, rows_written=:written,"
            " rows_skipped=:skipped, finished_at=now()"
            " WHERE lo = :lo".format(table=PROGRESS_TABLE)
        ),
        {"lo": lo, "state": state, "written": written, "skipped": skipped},
    )


def requeue_stale(ingest_db: IngestDB, older_than: str = "6 hours") -> int:
    """Return ranges from workers that died back to the queue.

    Not automatic and not on a short timer: a slow range and a dead worker look
    identical, and two workers on one range is worse than one range waiting.
    """
    result = ingest_db.execute(
        sql.text(
            "UPDATE {table} SET state='pending', claimed_by=NULL, claimed_at=NULL"
            " WHERE state='running' AND claimed_at < now() - CAST(:age AS interval)".format(
                table=PROGRESS_TABLE
            )
        ),
        {"age": older_than},
    )
    return result.rowcount


# --- validation -------------------------------------------------------------


@dataclass
class Diff:
    compared: int = 0
    mismatched: int = 0
    by_column: dict[str, int] = field(default_factory=dict)
    track_merged: int = 0
    track_genuine: int = 0
    missing_native: int = 0

    def add(self, other: "Diff") -> None:
        self.compared += other.compared
        self.mismatched += other.mismatched
        self.track_merged += other.track_merged
        self.track_genuine += other.track_genuine
        self.missing_native += other.missing_native
        for column, count in other.by_column.items():
            self.by_column[column] = self.by_column.get(column, 0) + count


def _merge_targets(
    fingerprint_db: FingerprintDB, track_ids: Sequence[int]
) -> dict[int, int]:
    """Map each track to where it ended up, following track.new_id.

    Chains are one hop in practice -- only four tracks in the database point at
    another merged track -- so this stops after a few rounds rather than
    walking indefinitely.
    """
    targets = {track_id: track_id for track_id in set(track_ids)}
    frontier = set(targets)
    for _ in range(4):
        moved = {
            track_id: new_id
            for track_id, new_id in _lookup(
                fingerprint_db, "track", "id", "new_id", frontier
            ).items()
            if new_id is not None
        }
        if not moved:
            break
        for track_id, current in targets.items():
            if current in moved:
                targets[track_id] = moved[current]
        frontier = set(moved.values())
    return targets


def compare_batch(
    ingest_db: IngestDB, fingerprint_db: FingerprintDB, rows: Sequence[Row]
) -> tuple[Diff, list[dict[str, Any]]]:
    """Diff reconstructed rows against the native ones for the same ids."""
    diff = Diff()
    if not rows:
        return diff, []

    ids = [row.submission_id for row in rows]
    native = {
        r.submission_id: r
        for r in ingest_db.execute(
            sql.text(
                "SELECT * FROM submission_result"
                " WHERE submission_id = ANY(CAST(:ids AS integer[]))"
            ),
            {"ids": ids},
        )
    }

    mismatched_tracks = []
    records = []
    for row in rows:
        want = native.get(row.submission_id)
        if want is None:
            diff.missing_native += 1
            continue
        diff.compared += 1
        differing = [
            column
            for column in COMPARED_COLUMNS
            if getattr(row, column) != getattr(want, column)
        ]
        if not differing:
            continue
        diff.mismatched += 1
        for column in differing:
            diff.by_column[column] = diff.by_column.get(column, 0) + 1
        if "track_id" in differing:
            mismatched_tracks.append((want.track_id, row.track_id))
        records.append(
            {
                "submission_id": row.submission_id,
                "columns": ",".join(differing),
                "native": {c: str(getattr(want, c)) for c in differing},
                "rebuilt": {c: str(getattr(row, c)) for c in differing},
            }
        )

    # A track merged after import legitimately reads back as a different id.
    # Counting those with genuine mapping errors would let a small real number
    # hide inside a large expected one.
    if mismatched_tracks:
        targets = _merge_targets(fingerprint_db, [n for n, _ in mismatched_tracks])
        for native_track, rebuilt_track in mismatched_tracks:
            if targets.get(native_track) == rebuilt_track:
                diff.track_merged += 1
            else:
                diff.track_genuine += 1

    return diff, records


# --- drivers ----------------------------------------------------------------


def _batches(lo: int, hi: int, batch_size: int) -> Iterator[list[int]]:
    """Submission ids in windows.

    The id space is ~95% dense in fingerprint_source, so walking it directly
    beats paging through a DISTINCT query and keeps no cursor state.
    """
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    for start in range(lo, hi, batch_size):
        yield list(range(start, min(start + batch_size, hi)))


def run_validate(
    script: Script,
    lo: int,
    hi: int,
    batch_size: int = DEFAULT_BATCH_SIZE,
    gid_table: str = GID_TABLE,
    examples: int = 20,
) -> Diff:
    """Reconstruct a range that already has native rows, and diff against them."""
    total = Diff()
    skipped = Skipped()
    cache: dict[int, Any] = {}
    shown = 0

    for ids in _batches(lo, hi, batch_size):
        with script.context() as ctx:
            ingest_db = ctx.db.get_ingest_db(read_only=True)
            fingerprint_db = ctx.db.get_fingerprint_db(read_only=True)
            rows, batch_skipped = build_rows(
                ingest_db,
                fingerprint_db,
                ctx.db.get_app_db(read_only=True),
                ids,
                cache,
                gid_table,
            )
            diff, records = compare_batch(ingest_db, fingerprint_db, rows)
        total.add(diff)
        skipped.no_fingerprint += batch_skipped.no_fingerprint
        skipped.no_source += batch_skipped.no_source
        for record in records:
            if shown >= examples:
                break
            logger.info(
                "submission %s differs on %s: native=%s rebuilt=%s",
                record["submission_id"],
                record["columns"],
                record["native"],
                record["rebuilt"],
            )
            shown += 1

    logger.info(
        "Compared %d rows, %d differed (%.4f%%)",
        total.compared,
        total.mismatched,
        100.0 * total.mismatched / total.compared if total.compared else 0.0,
    )
    for column in COMPARED_COLUMNS:
        count = total.by_column.get(column, 0)
        if count:
            logger.info(
                "  %-20s %d (%.4f%%)",
                column,
                count,
                100.0 * count / total.compared if total.compared else 0.0,
            )
    logger.info(
        "track_id differences: %d from merges, %d genuine",
        total.track_merged,
        total.track_genuine,
    )
    logger.info(
        "%d reconstructed rows had no native row; %d submissions could not be built "
        "(%d no fingerprint, %d no source)",
        total.missing_native,
        skipped.total(),
        skipped.no_fingerprint,
        skipped.no_source,
    )
    return total


def run_backfill(
    script: Script,
    worker: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    gid_table: str = GID_TABLE,
    max_ranges: int | None = None,
) -> tuple[int, int]:
    """Claim ranges from the queue and write them.

    Ranges come out in ascending id order, so a run starts with the oldest
    submissions -- the ones furthest from the watershed and least likely to
    have a native row.  Stops after *max_ranges* if given, always between
    ranges, leaving the rest pending and nothing half-written.
    """
    if script.config.cluster.role != "master":
        logger.info("Not running backfill_submission_result in replica mode")
        return 0, 0

    cache: dict[int, Any] = {}
    total_written = 0
    total_skipped = 0
    done_ranges = 0

    while max_ranges is None or done_ranges < max_ranges:
        with script.context() as ctx:
            claimed = claim_range(ctx.db.get_ingest_db(), worker)
            ctx.db.session.commit()
        if claimed is None:
            break
        lo, hi = claimed
        logger.info("Claimed %d..%d", lo, hi)

        written = 0
        skipped = Skipped()
        try:
            for ids in _batches(lo, hi, batch_size):
                with script.context() as ctx:
                    ingest_db = ctx.db.get_ingest_db()
                    rows, batch_skipped = build_rows(
                        ingest_db,
                        ctx.db.get_fingerprint_db(read_only=True),
                        ctx.db.get_app_db(read_only=True),
                        ids,
                        cache,
                        gid_table,
                    )
                    written += insert_rows(ingest_db, rows)
                    ctx.db.session.commit()
                skipped.no_fingerprint += batch_skipped.no_fingerprint
                skipped.no_source += batch_skipped.no_source
        except Exception:
            # Otherwise the range sits in 'running' looking like a slow worker,
            # and only comes back after the requeue age -- which is exactly the
            # distinction requeue_stale is careful not to guess at.
            logger.exception("Range %d..%d failed after %d rows", lo, hi, written)
            with script.context() as ctx:
                finish_range(
                    ctx.db.get_ingest_db(), lo, written, skipped.total(), state="failed"
                )
                ctx.db.session.commit()
            raise

        with script.context() as ctx:
            finish_range(ctx.db.get_ingest_db(), lo, written, skipped.total())
            ctx.db.session.commit()
        logger.info(
            "Finished %d..%d: %d written, %d skipped", lo, hi, written, skipped.total()
        )
        total_written += written
        total_skipped += skipped.total()
        done_ranges += 1

    logger.info("Done: %d rows written, %d skipped", total_written, total_skipped)
    return total_written, total_skipped


def watershed(ingest_db: IngestDB) -> int | None:
    """The oldest submission that has a native result row.

    Everything below it is what needs reconstructing; everything above it is
    the ground truth --validate compares against.
    """
    return ingest_db.execute(
        sql.text("SELECT min(submission_id) FROM submission_result")
    ).scalar()
