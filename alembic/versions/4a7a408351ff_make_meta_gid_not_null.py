"""make meta.gid not null

The dedup finished on 2026-09-12: 206,838,911 rows merged, 0 deferred and
duplicates_remaining = 0 across the whole id space.  All 180,629,760 rows in
meta have a gid, and none can be inserted without one -- find_or_insert_meta
sets it on INSERT, nothing updates or deletes it, and submission.py:257 is the
only writer in production.  The write path already holds the invariant; this
records it.

Production has the constraint already, applied by hand ahead of this revision
and stamped, using the sequence PG 18 added for the purpose:

    ALTER TABLE meta ADD CONSTRAINT meta_gid_not_null NOT NULL gid NOT VALID;
    ALTER TABLE meta VALIDATE CONSTRAINT meta_gid_not_null;
    ALTER TABLE meta ALTER COLUMN gid SET NOT NULL;

which validates under SHARE UPDATE EXCLUSIVE and blocks neither readers nor
writers.  The plain SET NOT NULL below takes ACCESS EXCLUSIVE for a full scan,
which on a 27 GB heap is an outage -- it is fine here because every database
that runs it is empty or small.  Do not point this revision at production
instead of stamping it.

init-db runs `alembic upgrade head`, so this is what gives a fresh database the
constraint; the test suite builds its schema with metadata.create_all, so
tables.py carries nullable=False for that.  Both are load-bearing, for
different consumers.

Revision ID: 4a7a408351ff
Revises: d3b8f5a21c74
Create Date: 2026-09-12 18:37:02.540516

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "4a7a408351ff"
down_revision = "d3b8f5a21c74"
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_app():
    pass


def downgrade_app():
    pass


def upgrade_ingest():
    pass


def downgrade_ingest():
    pass


def upgrade_fingerprint():
    op.alter_column("meta", "gid", existing_type=sa.UUID(), nullable=False)


def downgrade_fingerprint():
    op.alter_column("meta", "gid", existing_type=sa.UUID(), nullable=True)
