"""stats_lookups unique index on (date, hour, application_id)

Revision ID: f1a6d28c3b94
Revises: e3b7c94a1f62
Create Date: 2026-11-25 18:00:00.000000

The upsert in update_lookup_stats has always depended on this index, but no
migration created it. Databases that already have it can skip this one.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "f1a6d28c3b94"
down_revision = "e3b7c94a1f62"
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_app():
    op.create_index(
        "stats_lookups_idx_date_hour_application_id",
        "stats_lookups",
        ["date", "hour", "application_id"],
        unique=True,
    )


def downgrade_app():
    op.drop_index(
        "stats_lookups_idx_date_hour_application_id", table_name="stats_lookups"
    )


def upgrade_ingest():
    pass


def downgrade_ingest():
    pass


def upgrade_fingerprint():
    pass


def downgrade_fingerprint():
    pass
