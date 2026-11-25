"""account_application_key

Revision ID: c41d7e9a2b58
Revises: b7c3f1a84e26
Create Date: 2026-11-25 12:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c41d7e9a2b58"
down_revision = "b7c3f1a84e26"
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_app():
    op.create_table(
        "account_application_key",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("apikey", sa.String(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("device", sa.String(), nullable=True),
        sa.Column(
            "created",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("link_code", sa.String(), nullable=True),
        sa.Column("link_expires", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved", sa.DateTime(timezone=True), nullable=True),
        sa.Column("declined", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used", sa.Date(), nullable=True),
        sa.CheckConstraint(
            "(account_id IS NULL) = (approved IS NULL)",
            name="account_application_key_check_approved",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("account_application_key_fk_account_id"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["application.id"],
            name=op.f("account_application_key_fk_application_id"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("account_application_key_pkey")),
    )
    op.create_index(
        "account_application_key_idx_apikey",
        "account_application_key",
        ["apikey"],
        unique=True,
    )
    op.create_index(
        "account_application_key_idx_link_code",
        "account_application_key",
        ["link_code"],
        unique=True,
    )
    op.create_index(
        "account_application_key_idx_account_id",
        "account_application_key",
        ["account_id"],
        unique=False,
    )


def downgrade_app():
    op.drop_table("account_application_key")


def upgrade_ingest():
    pass


def downgrade_ingest():
    pass


def upgrade_fingerprint():
    pass


def downgrade_fingerprint():
    pass
