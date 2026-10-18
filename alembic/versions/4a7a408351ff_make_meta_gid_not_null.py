"""make meta.gid not null

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
    # Not a plain SET NOT NULL, which cannot be run on this table.
    #
    # SET NOT NULL takes ACCESS EXCLUSIVE and full-scans to verify. meta is
    # 180,751,856 rows and 27 GB, so at the ~100 MB/s a scan of it achieves
    # that is four to five minutes of lock. ACCESS EXCLUSIVE blocks reads as
    # well as writes, and meta sits in the lookup path, so running it that way
    # is a user-facing outage -- which is why this migration has been deferred
    # since September rather than applied.
    #
    # Since Postgres 12 a validated CHECK proving the same invariant lets
    # SET NOT NULL skip its scan. VALIDATE CONSTRAINT does the scanning under
    # SHARE UPDATE EXCLUSIVE, which blocks neither reads nor writes and can be
    # cancelled, and SET NOT NULL is then instant. Measured on a 4M-row stand
    # in: 843 ms of ACCESS EXCLUSIVE before, 9 ms after, with the scan moved
    # into a 1.3 s non-blocking VALIDATE. Lock levels confirmed from pg_locks,
    # including that a concurrent SELECT succeeds during VALIDATE and is
    # blocked during a plain SET NOT NULL.
    # Named tmp_ rather than meta_gid_not_null deliberately. Postgres 18
    # gives the column's NOT NULL its own catalogued constraint and wants
    # exactly that name for it, so a helper holding the name gets the column
    # constraint renamed to meta_gid_not_null1 and leaves it that way after
    # the helper is dropped. Found by running this rather than reading it.
    op.execute(
        "ALTER TABLE meta ADD CONSTRAINT tmp_meta_gid_not_null "
        "CHECK (gid IS NOT NULL) NOT VALID"
    )
    op.execute("ALTER TABLE meta VALIDATE CONSTRAINT tmp_meta_gid_not_null")
    op.execute("ALTER TABLE meta ALTER COLUMN gid SET NOT NULL")
    # The column constraint now carries the invariant, so the CHECK that was
    # only there to prove it is redundant.
    op.execute("ALTER TABLE meta DROP CONSTRAINT tmp_meta_gid_not_null")


def downgrade_fingerprint():
    op.alter_column("meta", "gid", existing_type=sa.UUID(), nullable=True)
