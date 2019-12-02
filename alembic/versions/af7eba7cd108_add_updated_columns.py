"""add updated columns

Revision ID: af7eba7cd108
Revises: d2176bc400c8
Create Date: 2019-12-02 07:44:04.212957

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'af7eba7cd108'
down_revision = 'd2176bc400c8'
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
    op.add_column(u'fingerprint', sa.Column('updated', sa.DateTime(timezone=True), nullable=True))
    op.add_column(u'track_foreignid', sa.Column('updated', sa.DateTime(timezone=True), nullable=True))
    op.add_column(u'track_mbid', sa.Column('updated', sa.DateTime(timezone=True), nullable=True))
    op.add_column(u'track_meta', sa.Column('updated', sa.DateTime(timezone=True), nullable=True))
    op.add_column(u'track_puid', sa.Column('updated', sa.DateTime(timezone=True), nullable=True))


def downgrade_fingerprint():
    op.drop_column(u'track_puid', 'updated')
    op.drop_column(u'track_meta', 'updated')
    op.drop_column(u'track_mbid', 'updated')
    op.drop_column(u'track_foreignid', 'updated')
    op.drop_column(u'fingerprint', 'updated')
