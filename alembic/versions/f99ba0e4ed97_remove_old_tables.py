"""remove old tables

Revision ID: f99ba0e4ed97
Revises: ae7e1e5763ef
Create Date: 2019-09-14 15:18:20.248950

"""

# revision identifiers, used by Alembic.
revision = 'f99ba0e4ed97'
down_revision = 'ae7e1e5763ef'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.drop_table('track_mbid_flag')
    op.drop_table('fingerprint_index_queue')
    op.drop_table('replication_control')
    op.drop_table('mirror_queue')
    op.drop_table('acoustid_mb_replication_control')


def downgrade():
    op.create_table('acoustid_mb_replication_control',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('current_schema_sequence', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('current_replication_sequence', sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column('last_replication_date', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
        sa.PrimaryKeyConstraint('id', name=u'acoustid_mb_replication_control_pkey')
    )
    op.create_table('mirror_queue',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('txid', sa.BIGINT(), server_default=sa.text(u'txid_current()'), autoincrement=False, nullable=False),
        sa.Column('tblname', sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column('op', sa.CHAR(length=1), autoincrement=False, nullable=False),
        sa.Column('data', sa.TEXT(), autoincrement=False, nullable=False),
        sa.PrimaryKeyConstraint('id', name=u'mirror_queue_pkey')
    )
    op.create_table('replication_control',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('current_schema_sequence', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('current_replication_sequence', sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column('last_replication_date', postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True),
        sa.PrimaryKeyConstraint('id', name=u'replication_control_pkey')
    )
    op.create_table('fingerprint_index_queue',
        sa.Column('fingerprint_id', sa.INTEGER(), autoincrement=False, nullable=False)
    )
    op.create_table('track_mbid_flag',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('track_mbid_id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('account_id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('handled', sa.BOOLEAN(), server_default=sa.text(u'false'), autoincrement=False, nullable=False),
        sa.Column('created', postgresql.TIMESTAMP(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(['account_id'], [u'account.id'], name=u'track_mbid_flag_fk_account_id'),
        sa.ForeignKeyConstraint(['track_mbid_id'], [u'track_mbid.id'], name=u'track_mbid_flag_fk_track_mbid_id'),
        sa.PrimaryKeyConstraint('id', name=u'track_mbid_flag_pkey')
    )
