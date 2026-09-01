#!/usr/bin/env python

# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""One-off deduplication of the meta table.

Most meta rows predate `gid` and were never deduplicated, so the same metadata
exists many times over under different ids. This collapses each set of rows
that share a computed gid into one, repointing everything that referred to the
others, and is the set-based equivalent of acoustid/scripts/backfill_meta_gid.py,
which defines the semantics and does the same work one row at a time.

Input is `tmp_meta_gid(id, gid)`, holding the recomputed gid for every meta row,
built and verified separately. Nothing here recomputes a gid.

Nothing sets `track_meta.updated`. Repointing a row does change what it points
at, but the daily export puts a row in the file for the day matching its
current `updated`, so touching it would pull tens of millions of rows out of
their own days and pile them into one. The new state reaches consumers through
a full re-export instead.

Every statement is idempotent and the phases are strictly ordered, so a failed
run is resumed by running it again. That is what makes two-phase commit
unnecessary here, unlike the row-at-a-time version: nothing depends on two
databases changing together, only on the order they change in.
"""

import logging
from typing import Iterator, Optional, Sequence

from sqlalchemy import sql

from acoustid.db import FingerprintDB, IngestDB
from acoustid.script import Script

logger = logging.getLogger(__name__)

# Built by this script, in the fingerprint database. Scratch, drop when done.
MAP_TABLE = "meta_dedup_map"
TRACK_META_SURVIVOR_TABLE = "meta_dedup_track_meta_survivor"
TRACK_META_LOSER_TABLE = "meta_dedup_track_meta_loser"
PROGRESS_TABLE = "meta_dedup_progress"

# Supplied, not built here.
SOURCE_TABLE = "tmp_meta_gid"

DEFAULT_CHUNK_SIZE = 1_000_000

PHASES = (
    "check",
    "plan",
    "gids",
    "track-meta",
    "repoint",
    "submissions",
    "delete",
)


SCRATCH_DDL = """
CREATE TABLE IF NOT EXISTS {map_table} (
    old_id integer PRIMARY KEY,
    new_id integer NOT NULL,
    gid uuid NOT NULL
);
CREATE INDEX IF NOT EXISTS {map_table}_idx_new_id ON {map_table} (new_id);

CREATE TABLE IF NOT EXISTS {survivor_table} (
    track_meta_id integer PRIMARY KEY,
    submission_count integer NOT NULL
);

CREATE TABLE IF NOT EXISTS {loser_table} (
    track_meta_id integer PRIMARY KEY,
    survivor_id integer NOT NULL
);

CREATE TABLE IF NOT EXISTS {progress_table} (
    phase text NOT NULL,
    lo integer NOT NULL,
    hi integer NOT NULL,
    done_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (phase, lo)
);
""".format(
    map_table=MAP_TABLE,
    survivor_table=TRACK_META_SURVIVOR_TABLE,
    loser_table=TRACK_META_LOSER_TABLE,
    progress_table=PROGRESS_TABLE,
)


SCRATCH_TABLES = (
    MAP_TABLE,
    TRACK_META_SURVIVOR_TABLE,
    TRACK_META_LOSER_TABLE,
    PROGRESS_TABLE,
)


def drop_scratch_tables(fingerprint_db: FingerprintDB) -> None:
    """Throw away the plan and the progress, so the next run decides again.

    The plan is deliberately sticky -- that is what makes a failed run
    resumable -- so there has to be a way to say the input it was built from
    was wrong.
    """
    for table in SCRATCH_TABLES:
        logger.info("Dropping %s", table)
        fingerprint_db.execute(sql.text("DROP TABLE IF EXISTS %s" % table))


def create_scratch_tables(fingerprint_db: FingerprintDB) -> None:
    for statement in SCRATCH_DDL.strip().split(";\n"):
        if statement.strip():
            fingerprint_db.execute(sql.text(statement))


def chunks(lo: int, hi: int, size: int) -> Iterator[tuple[int, int]]:
    """Inclusive ranges covering [lo, hi]."""
    while lo <= hi:
        yield lo, min(lo + size - 1, hi)
        lo += size


def done_chunks(fingerprint_db: FingerprintDB, phase: str) -> set[int]:
    rows = fingerprint_db.execute(
        sql.text("SELECT lo FROM %s WHERE phase = :phase" % PROGRESS_TABLE),
        {"phase": phase},
    )
    return {row[0] for row in rows}


def mark_chunk_done(
    fingerprint_db: FingerprintDB, phase: str, lo: int, hi: int
) -> None:
    fingerprint_db.execute(
        sql.text(
            "INSERT INTO %s (phase, lo, hi) VALUES (:phase, :lo, :hi)"
            " ON CONFLICT (phase, lo) DO NOTHING" % PROGRESS_TABLE
        ),
        {"phase": phase, "lo": lo, "hi": hi},
    )


def bounds(
    fingerprint_db: FingerprintDB, table: str, column: str
) -> Optional[tuple[int, int]]:
    row = fingerprint_db.execute(
        sql.text("SELECT min(%s), max(%s) FROM %s" % (column, column, table))
    ).one()
    if row[0] is None:
        return None
    return int(row[0]), int(row[1])


def check(fingerprint_db: FingerprintDB) -> None:
    """Refuse to touch anything unless the input is complete and agrees with
    the gids that are already there.

    A row that already carries a gid is an oracle: the recomputation has to
    reproduce it. If it does not, the computation is wrong and running the rest
    would merge rows that are not duplicates.
    """
    # Coverage, not equality: once the delete phase has run, the input still
    # describes rows that are gone, and a resumed run has to be able to get
    # past this. What matters is that no surviving meta row is missing one.
    uncovered = fingerprint_db.execute(
        sql.text(
            "SELECT count(*) FROM meta m"
            " LEFT JOIN %s t ON t.id = m.id WHERE t.id IS NULL" % SOURCE_TABLE
        )
    ).scalar_one()
    if uncovered:
        raise RuntimeError(
            "%s meta rows have no row in %s, it is not finished"
            % (uncovered, SOURCE_TABLE)
        )

    duplicates = fingerprint_db.execute(
        sql.text(
            "SELECT count(*) FROM (SELECT id FROM %s GROUP BY id HAVING count(*) > 1)"
            " x" % SOURCE_TABLE
        )
    ).scalar_one()
    if duplicates:
        raise RuntimeError("%s has %s duplicated ids" % (SOURCE_TABLE, duplicates))

    mismatched = fingerprint_db.execute(
        sql.text(
            "SELECT count(*) FROM meta m JOIN %s t ON t.id = m.id"
            " WHERE m.gid IS NOT NULL AND m.gid <> t.gid" % SOURCE_TABLE
        )
    ).scalar_one()
    if mismatched:
        raise RuntimeError(
            "%s rows disagree with the gid already stored on meta" % mismatched
        )
    logger.info("Input checks passed")


def plan(fingerprint_db: FingerprintDB) -> None:
    """Decide every survivor up front, once.

    This has to be a single global pass rather than chunked work: a set of
    duplicates is spread over the whole id space, and `meta.gid` is unique, so
    two workers deciding independently would race on it. Once the map exists
    everything after it is a replayable update driven off a fixed decision.
    """
    existing = fingerprint_db.execute(
        sql.text("SELECT count(*) FROM %s" % MAP_TABLE)
    ).scalar_one()
    if existing:
        logger.info("%s already holds %s rows, leaving it alone", MAP_TABLE, existing)
        return

    logger.info("Building %s", MAP_TABLE)
    fingerprint_db.execute(
        sql.text(
            """
            INSERT INTO {map_table} (old_id, new_id, gid)
            SELECT t.id, s.survivor_id, t.gid
            FROM {source} t
            JOIN (
                SELECT t.gid,
                       -- meta.gid is unique, so at most one row per group has
                       -- one; that row is the survivor because it is the id
                       -- already published and referred to.
                       coalesce(
                           min(m.id) FILTER (WHERE m.gid IS NOT NULL),
                           min(t.id)
                       ) AS survivor_id
                FROM {source} t
                JOIN meta m ON m.id = t.id
                GROUP BY t.gid
                HAVING count(*) > 1
            ) s ON s.gid = t.gid
            WHERE t.id <> s.survivor_id
            """.format(
                map_table=MAP_TABLE, source=SOURCE_TABLE
            )
        )
    )
    total = fingerprint_db.execute(
        sql.text("SELECT count(*) FROM %s" % MAP_TABLE)
    ).scalar_one()
    survivors = fingerprint_db.execute(
        sql.text("SELECT count(DISTINCT new_id) FROM %s" % MAP_TABLE)
    ).scalar_one()
    logger.info("%s rows collapse into %s survivors", total, survivors)


def assign_gids(
    fingerprint_db: FingerprintDB, ingest_db: IngestDB, chunk_size: int
) -> None:
    """Give a gid to every row that is keeping its id and does not have one."""
    span = bounds(fingerprint_db, "meta", "id")
    if span is None:
        return
    already = done_chunks(fingerprint_db, "gids")
    for lo, hi in chunks(span[0], span[1], chunk_size):
        if lo in already:
            continue
        result = fingerprint_db.execute(
            sql.text(
                """
                UPDATE meta SET gid = t.gid
                FROM {source} t
                WHERE meta.id = t.id
                  AND meta.id BETWEEN :lo AND :hi
                  AND meta.gid IS NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM {map_table} m WHERE m.old_id = meta.id
                  )
                """.format(
                    source=SOURCE_TABLE, map_table=MAP_TABLE
                )
            ),
            {"lo": lo, "hi": hi},
        )
        logger.info("gids: %s..%s, %s rows", lo, hi, result.rowcount)
        mark_chunk_done(fingerprint_db, "gids", lo, hi)


def plan_track_meta(fingerprint_db: FingerprintDB, chunk_size: int) -> None:
    """Work out which track_meta rows collapse into which.

    `track_meta` is unique on (track_id, meta_id), so repointing alone is not
    enough: once two meta ids become one, a track linked to both would end up
    with two identical links. Grouping on the resolved meta id covers that and
    the case the row-at-a-time version only handles incidentally, where a track
    is linked to two rows that both disappear into the same survivor.

    Chunked by track_id because a group never spans one.
    """
    existing = fingerprint_db.execute(
        sql.text("SELECT count(*) FROM %s" % TRACK_META_LOSER_TABLE)
    ).scalar_one()
    if existing:
        logger.info("track_meta plan already built, %s losers", existing)
        return

    span = bounds(fingerprint_db, "track_meta", "track_id")
    if span is None:
        return
    for lo, hi in chunks(span[0], span[1], chunk_size):
        fingerprint_db.execute(
            sql.text(
                """
                WITH resolved AS (
                    SELECT tm.id, tm.track_id, tm.submission_count,
                           coalesce(m.new_id, tm.meta_id) AS meta_id
                    FROM track_meta tm
                    LEFT JOIN {map_table} m ON m.old_id = tm.meta_id
                    WHERE tm.track_id BETWEEN :lo AND :hi
                ),
                grouped AS (
                    SELECT track_id, meta_id,
                           min(id) AS survivor_id,
                           sum(submission_count) AS total_count
                    FROM resolved
                    GROUP BY track_id, meta_id
                    HAVING count(*) > 1
                ),
                ins_survivor AS (
                    INSERT INTO {survivor_table} (track_meta_id, submission_count)
                    SELECT survivor_id, total_count FROM grouped
                    ON CONFLICT (track_meta_id) DO NOTHING
                    RETURNING 1
                )
                INSERT INTO {loser_table} (track_meta_id, survivor_id)
                SELECT r.id, g.survivor_id
                FROM resolved r
                JOIN grouped g
                  ON g.track_id = r.track_id AND g.meta_id = r.meta_id
                WHERE r.id <> g.survivor_id
                ON CONFLICT (track_meta_id) DO NOTHING
                """.format(
                    map_table=MAP_TABLE,
                    survivor_table=TRACK_META_SURVIVOR_TABLE,
                    loser_table=TRACK_META_LOSER_TABLE,
                )
            ),
            {"lo": lo, "hi": hi},
        )
    losers = fingerprint_db.execute(
        sql.text("SELECT count(*) FROM %s" % TRACK_META_LOSER_TABLE)
    ).scalar_one()
    logger.info("track_meta plan: %s rows collapse", losers)


def collapse_track_meta(
    fingerprint_db: FingerprintDB, ingest_db: IngestDB, chunk_size: int
) -> None:
    """Apply the plan: absolute counts, then sources, then delete.

    The count is set to the group total rather than added to, so re-running a
    chunk that failed halfway cannot double it.
    """
    span = bounds(fingerprint_db, TRACK_META_LOSER_TABLE, "track_meta_id")
    if span is None:
        logger.info("Nothing to collapse")
        return
    already = done_chunks(fingerprint_db, "track-meta")
    for lo, hi in chunks(span[0], span[1], chunk_size):
        if lo in already:
            continue

        fingerprint_db.execute(
            sql.text(
                """
                UPDATE track_meta SET submission_count = s.submission_count
                FROM {survivor_table} s
                WHERE track_meta.id = s.track_meta_id
                  AND s.track_meta_id IN (
                      SELECT survivor_id FROM {loser_table}
                      WHERE track_meta_id BETWEEN :lo AND :hi
                  )
                """.format(
                    survivor_table=TRACK_META_SURVIVOR_TABLE,
                    loser_table=TRACK_META_LOSER_TABLE,
                )
            ),
            {"lo": lo, "hi": hi},
        )

        losers = [
            (row[0], row[1])
            for row in fingerprint_db.execute(
                sql.text(
                    "SELECT track_meta_id, survivor_id FROM %s"
                    " WHERE track_meta_id BETWEEN :lo AND :hi" % TRACK_META_LOSER_TABLE
                ),
                {"lo": lo, "hi": hi},
            )
        ]
        # track_meta_source lives in the ingest database, so this cannot be a
        # join. Repoint before deleting, or the sources are orphaned.
        repoint_track_meta_sources(ingest_db, losers)

        result = fingerprint_db.execute(
            sql.text(
                "DELETE FROM track_meta WHERE id IN ("
                "  SELECT track_meta_id FROM %s WHERE track_meta_id BETWEEN :lo AND :hi"
                ")" % TRACK_META_LOSER_TABLE
            ),
            {"lo": lo, "hi": hi},
        )
        logger.info("track-meta: %s..%s, %s rows deleted", lo, hi, result.rowcount)
        mark_chunk_done(fingerprint_db, "track-meta", lo, hi)


def repoint_track_meta_sources(
    ingest_db: IngestDB, losers: Sequence[tuple[int, int]]
) -> None:
    if not losers:
        return
    values = ", ".join("(%d, %d)" % (old, new) for old, new in losers)
    ingest_db.execute(
        sql.text(
            "UPDATE track_meta_source SET track_meta_id = v.new_id"
            " FROM (VALUES %s) AS v(old_id, new_id)"
            " WHERE track_meta_source.track_meta_id = v.old_id" % values
        )
    )


def repoint_track_meta(fingerprint_db: FingerprintDB, chunk_size: int) -> None:
    """Everything that did not collapse just points somewhere else now."""
    span = bounds(fingerprint_db, MAP_TABLE, "old_id")
    if span is None:
        return
    already = done_chunks(fingerprint_db, "repoint")
    for lo, hi in chunks(span[0], span[1], chunk_size):
        if lo in already:
            continue
        result = fingerprint_db.execute(
            sql.text(
                """
                UPDATE track_meta SET meta_id = m.new_id
                FROM {map_table} m
                WHERE track_meta.meta_id = m.old_id
                  AND m.old_id BETWEEN :lo AND :hi
                """.format(
                    map_table=MAP_TABLE
                )
            ),
            {"lo": lo, "hi": hi},
        )
        logger.info("repoint: %s..%s, %s rows", lo, hi, result.rowcount)
        mark_chunk_done(fingerprint_db, "repoint", lo, hi)


def repoint_submissions(
    fingerprint_db: FingerprintDB, ingest_db: IngestDB, chunk_size: int
) -> None:
    """submission_result is in the ingest database, so the map has to travel."""
    span = bounds(fingerprint_db, MAP_TABLE, "old_id")
    if span is None:
        return
    already = done_chunks(fingerprint_db, "submissions")
    for lo, hi in chunks(span[0], span[1], chunk_size):
        if lo in already:
            continue
        mappings = [
            (row[0], row[1], str(row[2]))
            for row in fingerprint_db.execute(
                sql.text(
                    "SELECT old_id, new_id, gid FROM %s"
                    " WHERE old_id BETWEEN :lo AND :hi" % MAP_TABLE
                ),
                {"lo": lo, "hi": hi},
            )
        ]
        if mappings:
            values = ", ".join(
                "(%d, %d, '%s'::uuid)" % (old, new, gid) for old, new, gid in mappings
            )
            ingest_db.execute(
                sql.text(
                    "UPDATE submission_result SET meta_id = v.new_id,"
                    " meta_gid = v.gid"
                    " FROM (VALUES %s) AS v(old_id, new_id, gid)"
                    " WHERE submission_result.meta_id = v.old_id" % values
                )
            )
        logger.info("submissions: %s..%s, %s mappings", lo, hi, len(mappings))
        mark_chunk_done(fingerprint_db, "submissions", lo, hi)


def delete_meta(fingerprint_db: FingerprintDB, chunk_size: int) -> None:
    """Record where each id went, then drop it.

    Last, because track_meta has a foreign key to meta.
    """
    span = bounds(fingerprint_db, MAP_TABLE, "old_id")
    if span is None:
        return
    already = done_chunks(fingerprint_db, "delete")
    for lo, hi in chunks(span[0], span[1], chunk_size):
        if lo in already:
            continue
        fingerprint_db.execute(
            sql.text(
                "INSERT INTO meta_id_history (id, gid)"
                " SELECT old_id, gid FROM %s WHERE old_id BETWEEN :lo AND :hi"
                " ON CONFLICT (id) DO NOTHING" % MAP_TABLE
            ),
            {"lo": lo, "hi": hi},
        )
        result = fingerprint_db.execute(
            sql.text(
                "DELETE FROM meta WHERE id IN ("
                "  SELECT old_id FROM %s WHERE old_id BETWEEN :lo AND :hi"
                ")" % MAP_TABLE
            ),
            {"lo": lo, "hi": hi},
        )
        logger.info("delete: %s..%s, %s rows", lo, hi, result.rowcount)
        mark_chunk_done(fingerprint_db, "delete", lo, hi)


def dedup_meta(
    script: Script,
    phases: Sequence[str] = PHASES,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    reset: bool = False,
) -> None:
    for phase in phases:
        if phase not in PHASES:
            raise ValueError("unknown phase %r" % phase)

    if reset:
        with script.context() as ctx:
            drop_scratch_tables(ctx.db.get_fingerprint_db())
            ctx.db.session.commit()

    for phase in PHASES:
        if phase not in phases:
            continue
        logger.info("Phase %s", phase)
        with script.context() as ctx:
            fingerprint_db = ctx.db.get_fingerprint_db()
            ingest_db = ctx.db.get_ingest_db()
            create_scratch_tables(fingerprint_db)
            if phase == "check":
                check(fingerprint_db)
            elif phase == "plan":
                plan(fingerprint_db)
            elif phase == "gids":
                assign_gids(fingerprint_db, ingest_db, chunk_size)
            elif phase == "track-meta":
                plan_track_meta(fingerprint_db, chunk_size)
                collapse_track_meta(fingerprint_db, ingest_db, chunk_size)
            elif phase == "repoint":
                repoint_track_meta(fingerprint_db, chunk_size)
            elif phase == "submissions":
                repoint_submissions(fingerprint_db, ingest_db, chunk_size)
            elif phase == "delete":
                delete_meta(fingerprint_db, chunk_size)
            ctx.db.session.commit()


def run_dedup_meta(script, opts, args):
    # type: (Script, object, object) -> None
    if script.config.cluster.role != "master":
        logger.info("Not running dedup_meta in slave mode")
        return
    dedup_meta(script)
