"""stats_user_lookups

Revision ID: e3b7c94a1f62
Revises: d8a2f5c19e47
Create Date: 2026-11-25 17:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "e3b7c94a1f62"
down_revision = "d8a2f5c19e47"
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_app():
    op.create_table(
        "stats_user_lookups",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column(
            "count_hits", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "count_nohits", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["account.id"],
            name=op.f("stats_user_lookups_fk_account_id"),
        ),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["application.id"],
            name=op.f("stats_user_lookups_fk_application_id"),
        ),
        sa.PrimaryKeyConstraint(
            "date", "account_id", "application_id", name=op.f("stats_user_lookups_pkey")
        ),
    )


def downgrade_app():
    op.drop_table("stats_user_lookups")


def upgrade_ingest():
    pass


def downgrade_ingest():
    pass


def upgrade_fingerprint():
    pass


def downgrade_fingerprint():
    pass
