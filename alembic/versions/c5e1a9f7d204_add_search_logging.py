"""add search logging

Revision ID: c5e1a9f7d204
Revises: 4a7a408351ff
Create Date: 2026-10-16 13:10:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "c5e1a9f7d204"
down_revision = "4a7a408351ff"
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_app():
    op.create_table(
        "search_query",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("query", sa.String(), nullable=False),
        sa.Column("found", sa.Integer(), nullable=False),
        sa.Column("session", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("search_query_idx_created", "search_query", ["created"])
    op.create_table(
        "search_click",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("query_id", sa.BigInteger(), nullable=False),
        sa.Column("mbid", postgresql.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["search_query.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("search_click_idx_query_id", "search_click", ["query_id"])


def downgrade_app():
    op.drop_index("search_click_idx_query_id", table_name="search_click")
    op.drop_table("search_click")
    op.drop_index("search_query_idx_created", table_name="search_query")
    op.drop_table("search_query")


def upgrade_ingest():
    pass


def downgrade_ingest():
    pass


def upgrade_fingerprint():
    pass


def downgrade_fingerprint():
    pass
