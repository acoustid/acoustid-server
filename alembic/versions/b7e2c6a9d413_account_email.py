"""account.email, account_email_confirmation

Revision ID: b7e2c6a9d413
Revises: f1a6d28c3b94
Create Date: 2026-11-25 19:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b7e2c6a9d413"
down_revision = "f1a6d28c3b94"
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_app():
    op.add_column("account", sa.Column("email", sa.String(), nullable=True))
    op.add_column(
        "account",
        sa.Column("email_verified", sa.DateTime(timezone=True), nullable=True),
    )
    # No row matches the predicate yet, but the build still scans the table
    # and blocks writes to it meanwhile. It can be built by hand with CREATE
    # INDEX CONCURRENTLY beforehand, which is why this skips an existing one.
    op.create_index(
        "account_idx_email",
        "account",
        ["email"],
        unique=True,
        postgresql_where=sa.text("email_verified IS NOT NULL"),
        if_not_exists=True,
    )
    op.create_table(
        "account_email_confirmation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column(
            "created",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "account_email_confirmation_idx_token_hash",
        "account_email_confirmation",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "account_email_confirmation_idx_account_id",
        "account_email_confirmation",
        ["account_id"],
    )


def downgrade_app():
    op.drop_table("account_email_confirmation")
    op.drop_index("account_idx_email", table_name="account")
    op.drop_column("account", "email_verified")
    op.drop_column("account", "email")


def upgrade_ingest():
    pass


def downgrade_ingest():
    pass


def upgrade_fingerprint():
    pass


def downgrade_fingerprint():
    pass
