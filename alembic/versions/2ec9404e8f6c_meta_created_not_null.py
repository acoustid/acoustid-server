"""make meta.created not null

Revision ID: 2ec9404e8f6c
Revises: a1f4c72b90de
Create Date: 2026-09-01 10:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "2ec9404e8f6c"
down_revision = "a1f4c72b90de"
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
    op.alter_column(
        "meta",
        "created",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        nullable=False,
    )


def downgrade_fingerprint():
    op.alter_column(
        "meta",
        "created",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        server_default=None,
        nullable=True,
    )
