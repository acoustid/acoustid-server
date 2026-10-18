"""index track_mbid_change.created

Revision ID: a3f80c21e7b9
Revises: 4a7a408351ff
Create Date: 2026-10-18 09:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "a3f80c21e7b9"
down_revision = "4a7a408351ff"
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
    # The audit page lists changes newest first across the whole table, which
    # without this is a full scan and a sort on every page view.
    op.create_index("track_mbid_change_idx_created", "track_mbid_change", ["created"])


def downgrade_ingest():
    op.drop_index("track_mbid_change_idx_created", table_name="track_mbid_change")


def upgrade_fingerprint():
    pass


def downgrade_fingerprint():
    pass
