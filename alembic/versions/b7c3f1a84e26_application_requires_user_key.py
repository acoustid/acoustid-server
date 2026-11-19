"""application.requires_user_key

Revision ID: b7c3f1a84e26
Revises: a3f80c21e7b9
Create Date: 2026-11-19 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b7c3f1a84e26"
down_revision = "a3f80c21e7b9"
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_app():
    # Defaults to true, so every existing application is covered by the
    # user-key policy and the exceptions are set explicitly afterwards.
    # Postgres 11+ adds a NOT NULL column with a constant default without
    # rewriting the table, so this does not need the no-downtime dance that
    # meta.gid did -- and application is small regardless.
    op.add_column(
        "application",
        sa.Column(
            "requires_user_key",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
    )


def downgrade_app():
    op.drop_column("application", "requires_user_key")


def upgrade_ingest():
    pass


def downgrade_ingest():
    pass


def upgrade_fingerprint():
    pass


def downgrade_fingerprint():
    pass
