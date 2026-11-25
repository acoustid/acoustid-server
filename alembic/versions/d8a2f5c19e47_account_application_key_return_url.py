"""account_application_key.return_url

Revision ID: d8a2f5c19e47
Revises: c41d7e9a2b58
Create Date: 2026-11-25 16:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "d8a2f5c19e47"
down_revision = "c41d7e9a2b58"
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_app():
    op.add_column(
        "account_application_key",
        sa.Column("return_url", sa.String(), nullable=True),
    )
    op.create_index(
        "account_application_key_idx_application_id_pending",
        "account_application_key",
        ["application_id", "link_expires"],
        unique=False,
        postgresql_where=sa.text("link_code IS NOT NULL"),
    )


def downgrade_app():
    op.drop_index(
        "account_application_key_idx_application_id_pending",
        table_name="account_application_key",
    )
    op.drop_column("account_application_key", "return_url")


def upgrade_ingest():
    pass


def downgrade_ingest():
    pass


def upgrade_fingerprint():
    pass


def downgrade_fingerprint():
    pass
