#!/usr/bin/env python

# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Give each duplicate group's gid to one of its members.

34.4M groups of content-identical meta rows share 241M rows between them, and
most of those groups have nobody holding the gid. This gives each unclaimed
group's gid to its lowest-numbered surviving member.

WHY THIS IS WORTH DOING ON ITS OWN, AHEAD OF THE MERGE

It stops the duplicates growing. find_or_insert_meta resolves content by gid,
so while a group has no holder every resubmission of that content finds
nothing, inserts yet another row, and the group gets one member larger. Once
one member holds the gid, those submissions land on it instead. The merge can
then take as long as it needs against a set that is no longer moving.

It also makes the merge a materially easier thing to write. A group too large
for one transaction has to be merged in slices, and slicing is only dangerous
because the survivor is unknown when the merge starts -- two slices resolving
before either commits would pick different survivors. Once the gid is claimed,
the survivor is a fact in the database, every slice resolves to the same row
by lookup, and no ordering rule between slices is needed at all. The 211
groups holding 22.8M members between them were never hard because of their
size; they were hard because the survivor was unstable under slicing.

WHO GETS THE GID

The lowest surviving member, but only where nobody holds it yet.

If any row already holds the group's gid, that row is the group's primary and
the group is left alone. The holder need not be a member: a row created after
the snapshot with identical content holds the gid and is not in meta_ids at
all. Moving a gid off whatever holds it would invalidate everything already
grouped onto it, so an existing holder always wins.

"Lowest member" means lowest id that still exists and still has a NULL gid,
not lowest id in the snapshot array. Members have been deleted since it was
taken.

Measured: 14,803,922 groups already have a holder and 19,617,186 do not, so
this writes one row for each of the latter, whether the group has two members
or a hundred thousand.

About 9,400 of the already-held groups are held by a row that is NOT one of
their members -- which is why the rule below is what it is rather than simply
"lowest member".

THE DEAD TUPLES IT LEAVES WILL NOT BE VACUUMED BY THEMSELVES

Each claim is an UPDATE, so this leaves roughly 19.6M dead tuples on meta.
Autovacuum will not collect them: the default scale factor of 0.2 against
meta's ~388M rows puts the trigger near 77.6M dead tuples, so a job an order
of magnitude smaller never approaches it. The bloat sits until something else
triggers a vacuum on the table.

That is a few percent of a table that is now 95 GB -- it was 68 GB before the
singleton backfill, which left 27 GB of reusable but unreturned space behind.
Size anything on 95 GB rather than on the older figure.

Not an argument for doing this differently. It is here because the batching is
justified by transaction size -- standby replay, and the blast radius of a
failure -- and not by vacuum behaviour, and someone sizing a later job on this
table should not assume the space comes back on its own.

WHAT THIS DELIBERATELY DOES NOT DO

It does not merge anything, repoint any track_meta row, or delete anything.
After it runs, each group has exactly one row holding the gid and the rest
still NULL. That is the same state the collisions from the singleton backfill
are already in, and it is a resting state rather than a half-finished one.
"""

import logging
import re
import uuid

from sqlalchemy import sql

from acoustid.db import FingerprintDB
from acoustid.script import Script

logger = logging.getLogger(__name__)

# The duplicate groups, prepared out of band: one row per gid, with the meta
# ids that computed to it. Unique on gid, which is what makes the keyset walk
# below cheap.
DUPS_TABLE = "tmp_meta_dups"

# Created by init, removed by drop, and deliberately not declared in
# tables.py. meta_gid_backfill_status was exactly this kind of table declared
# alongside real schema, and it outlived its script by six years.
PROGRESS_TABLE = "meta_gid_claim_progress"

# Groups per transaction. Each claims at most one row, so this is a small
# write; the cost is the lookup of each group's members.
DEFAULT_BATCH_SIZE = 5000

ZERO_UUID = uuid.UUID(int=0)

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
            " last_gid uuid NOT NULL,"
            " groups_claimed bigint NOT NULL DEFAULT 0,"
            " updated timestamptz NOT NULL DEFAULT now()"
            ")".format(table=PROGRESS_TABLE)
        )
    )
    fingerprint_db.execute(
        sql.text(
            "INSERT INTO {table} (id, last_gid)"
            " VALUES (1, CAST(:zero AS uuid))"
            " ON CONFLICT (id) DO NOTHING".format(table=PROGRESS_TABLE)
        ),
        {"zero": str(ZERO_UUID)},
    )


def drop_progress(fingerprint_db: FingerprintDB) -> None:
    fingerprint_db.execute(
        sql.text("DROP TABLE IF EXISTS {t}".format(t=PROGRESS_TABLE))
    )


def get_progress(fingerprint_db: FingerprintDB) -> tuple[uuid.UUID, int]:
    row = fingerprint_db.execute(
        sql.text(
            "SELECT last_gid, groups_claimed FROM {t} WHERE id = 1".format(
                t=PROGRESS_TABLE
            )
        )
    ).first()
    if row is None:
        raise RuntimeError("%s is missing, run init first" % (PROGRESS_TABLE,))
    return row.last_gid, row.groups_claimed


def next_gid_bound(
    fingerprint_db: FingerprintDB,
    cursor: uuid.UUID,
    batch_size: int,
    dups_table: str = DUPS_TABLE,
) -> uuid.UUID | None:
    """The gid this batch runs up to, inclusive.

    The last of the ordered batch rather than max() over it, because
    PostgreSQL has no max aggregate for uuid, and nested rather than
    OFFSET :limit-1 LIMIT 1, because that returns nothing when fewer than
    batch_size groups remain -- which is every final batch, and would end the
    walk with the tail unclaimed.

    One row comes back rather than batch_size of them. The member arrays stay
    in the database either way; the largest holds 108,000 ids and there is no
    reason to carry those back and forth to learn where a batch ends.
    """
    return fingerprint_db.execute(
        sql.text(
            "SELECT gid FROM ("
            "  SELECT gid FROM {table} WHERE gid > CAST(:cursor AS uuid)"
            "   ORDER BY gid LIMIT :limit"
            ") t ORDER BY gid DESC LIMIT 1".format(table=check_table_name(dups_table))
        ),
        {"cursor": str(cursor), "limit": batch_size},
    ).scalar()


def claim_batch(
    fingerprint_db: FingerprintDB,
    lo: uuid.UUID,
    hi: uuid.UUID,
    dups_table: str = DUPS_TABLE,
) -> int:
    """Claim every unclaimed group in (lo, hi]. The caller commits.

    The cursor moves in the same transaction as the rows, so resuming is a
    record of progress rather than an approximation of it.
    """
    query = sql.text(
        "WITH batch AS ("
        "  SELECT gid, meta_ids FROM {table}"
        "   WHERE gid > CAST(:lo AS uuid) AND gid <= CAST(:hi AS uuid)"
        "),"
        " claimant AS ("
        "  SELECT b.gid, min(m.id) AS id"
        "    FROM batch b JOIN meta m ON m.id = ANY(b.meta_ids)"
        # Lowest member that still exists and has no gid of its own. A member
        # already holding the group's gid is excluded here and caught by the
        # guard below, which skips the group entirely.
        "   WHERE m.gid IS NULL"
        "   GROUP BY b.gid"
        " )"
        " UPDATE meta m SET gid = c.gid"
        "   FROM claimant c"
        "  WHERE m.id = c.id"
        "    AND m.gid IS NULL"
        # Somebody already holds this gid -- a member, or a row created since
        # the snapshot with identical content. Either way the group has its
        # primary and moving the gid would invalidate what is grouped on it.
        "    AND NOT EXISTS (SELECT 1 FROM meta m2 WHERE m2.gid = c.gid)".format(
            table=check_table_name(dups_table)
        )
    )
    claimed = fingerprint_db.execute(query, {"lo": str(lo), "hi": str(hi)}).rowcount
    fingerprint_db.execute(
        sql.text(
            "UPDATE {t} SET last_gid = CAST(:hi AS uuid),"
            " groups_claimed = groups_claimed + :claimed, updated = now()"
            " WHERE id = 1".format(t=PROGRESS_TABLE)
        ),
        {"hi": str(hi), "claimed": claimed},
    )
    return claimed


def report(
    fingerprint_db: FingerprintDB, dups_table: str = DUPS_TABLE
) -> tuple[int, int]:
    """Groups whose gid is held, and groups where it is not.

    Uses the ordinary connection rather than a read-only one: this probes
    meta_idx_gid once per group across 34.4M groups and takes minutes, which a
    hot standby would cancel as a recovery conflict.

    A group can be unclaimed after a completed run only if it has no surviving
    member left to hold the gid, so a nonzero count there is worth looking at
    rather than assuming.

    Counted as total minus claimed rather than with a second FILTER: two
    FILTERs compile to two subplans and probe meta_idx_gid twice per group,
    which on 34.4M groups is 68.8M lookups for two numbers that only need
    34.4M. The subplans are essentially the whole cost of this query.
    """
    row = fingerprint_db.execute(
        sql.text(
            "SELECT count(*) AS total,"
            "  count(*) FILTER ("
            "    WHERE EXISTS (SELECT 1 FROM meta m WHERE m.gid = d.gid)"
            "  ) AS claimed"
            " FROM {table} d".format(table=check_table_name(dups_table))
        )
    ).one()
    return row.claimed, row.total - row.claimed


def run_claim(
    script: Script,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
    dups_table: str = DUPS_TABLE,
) -> int:
    """Walk the groups from the cursor, claiming each one's gid."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if script.config.cluster.role != "master":
        logger.info("Not running claim_duplicate_gids in replica mode")
        return 0

    with script.context() as ctx:
        cursor, already = get_progress(ctx.db.get_fingerprint_db())
    logger.info("Resuming after %s, %d groups claimed so far", cursor, already)

    total = 0
    batches = 0
    while limit is None or batches < limit:
        with script.context() as ctx:
            fingerprint_db = ctx.db.get_fingerprint_db()
            hi = next_gid_bound(fingerprint_db, cursor, batch_size, dups_table)
            if hi is None:
                break
            claimed = claim_batch(fingerprint_db, cursor, hi, dups_table)
            ctx.db.session.commit()
        total += claimed
        batches += 1
        cursor = hi
        if batches % 100 == 0:
            logger.info("Reached %s, %d groups claimed this run", cursor, total)

    logger.info("Claimed %d groups in %d batches", total, batches)
    return total
