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
    # Not a plain SET NOT NULL. That takes ACCESS EXCLUSIVE and full-scans to
    # verify, which on a table this size blocks reads for minutes -- so this
    # migration has sat deferred rather than being applied. Since Postgres 12
    # a validated CHECK proving the same invariant lets SET NOT NULL skip its
    # scan, and VALIDATE CONSTRAINT does that scanning under SHARE UPDATE
    # EXCLUSIVE, blocking neither reads nor writes.
    #
    # The helper must not be named meta_gid_not_null: Postgres 18 wants that
    # name for the column's own NOT NULL constraint, so a helper holding it
    # leaves the column constraint called meta_gid_not_null1 after the helper
    # is dropped.
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
