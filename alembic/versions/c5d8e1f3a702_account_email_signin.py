"""account_email_signin

Revision ID: c5d8e1f3a702
Revises: b7e2c6a9d413
Create Date: 2026-11-25 21:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c5d8e1f3a702"
down_revision = "b7e2c6a9d413"
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_app():
    op.create_table(
        "account_email_signin",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("return_url", sa.String(), nullable=True),
        sa.Column(
            "code_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "created",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "account_email_signin_idx_token_hash",
        "account_email_signin",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "account_email_signin_idx_email_created",
        "account_email_signin",
        ["email", "created"],
    )


def downgrade_app():
    op.drop_table("account_email_signin")


def upgrade_ingest():
    pass


def downgrade_ingest():
    pass


def upgrade_fingerprint():
    pass


def downgrade_fingerprint():
    pass
