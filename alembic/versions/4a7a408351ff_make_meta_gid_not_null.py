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
    op.alter_column("meta", "gid", existing_type=sa.UUID(), nullable=False)


def downgrade_fingerprint():
    op.alter_column("meta", "gid", existing_type=sa.UUID(), nullable=True)
