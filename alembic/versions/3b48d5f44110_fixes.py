"""fixes

Revision ID: 3b48d5f44110
Revises: 57c4d22c87b8
Create Date: 2016-02-10 21:32:18.123976

"""

# revision identifiers, used by Alembic.
revision = '3b48d5f44110'
down_revision = '57c4d22c87b8'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_foreign_key(op.f('account_google_fk_account_id'), 'account_google', 'account', ['account_id'], ['id'])
    op.create_foreign_key(op.f('application_fk_account_id'), 'application', 'account', ['account_id'], ['id'])
    op.create_foreign_key(op.f('stats_lookups_fk_application_id'), 'stats_lookups', 'application', ['application_id'], ['id'])
    op.create_foreign_key(op.f('stats_user_agents_fk_application_id'), 'stats_user_agents', 'application', ['application_id'], ['id'])
    op.drop_index('track_foreignid_idx_uniq', table_name='track_foreignid')
    op.create_index('track_foreignid_idx_uniq', 'track_foreignid', ['track_id', 'foreignid_id'], unique=True)
    op.drop_index('track_mbid_idx_uniq', table_name='track_mbid')
    op.create_index('track_mbid_idx_uniq', 'track_mbid', ['track_id', 'mbid'], unique=True)
    op.drop_index('track_meta_idx_uniq', table_name='track_meta')
    op.create_index('track_meta_idx_uniq', 'track_meta', ['track_id', 'meta_id'], unique=True)
    op.drop_index('track_puid_idx_uniq', table_name='track_puid')
    op.create_index('track_puid_idx_uniq', 'track_puid', ['track_id', 'puid'], unique=True)
    op.alter_column('account', 'created', nullable=False)
    op.alter_column('application', 'created', nullable=False)
    op.alter_column('track', 'created', nullable=False)
    op.alter_column('fingerprint_source', 'created', nullable=False)
    op.alter_column('track_mbid', 'created', nullable=False)
    op.alter_column('track_mbid_source', 'created', nullable=False)
    op.alter_column('track_mbid_change', 'created', nullable=False)
    op.alter_column('track_mbid_flag', 'created', nullable=False)
    op.alter_column('track_puid', 'created', nullable=False)
    op.alter_column('track_puid_source', 'created', nullable=False)
    op.alter_column('track_meta', 'created', nullable=False)
    op.alter_column('track_meta_source', 'created', nullable=False)
    op.alter_column('track_foreignid', 'created', nullable=False)
    op.alter_column('track_foreignid_source', 'created', nullable=False)
    op.alter_column('recording_acoustid', 'created', nullable=False)


def downgrade():
    op.alter_column('recording_acoustid', 'created', nullable=True)
    op.alter_column('track_foreignid_source', 'created', nullable=True)
    op.alter_column('track_foreignid', 'created', nullable=True)
    op.alter_column('track_meta_source', 'created', nullable=True)
    op.alter_column('track_meta', 'created', nullable=True)
    op.alter_column('track_puid_source', 'created', nullable=True)
    op.alter_column('track_puid', 'created', nullable=True)
    op.alter_column('track_mbid_flag', 'created', nullable=True)
    op.alter_column('track_mbid_change', 'created', nullable=True)
    op.alter_column('track_mbid_source', 'created', nullable=True)
    op.alter_column('track_mbid', 'created', nullable=True)
    op.alter_column('fingerprint_source', 'created', nullable=True)
    op.alter_column('track', 'created', nullable=True)
    op.alter_column('application', 'created', nullable=True)
    op.alter_column('account', 'created', nullable=True)
    op.drop_index('track_puid_idx_uniq', table_name='track_puid')
    op.create_index('track_puid_idx_uniq', 'track_puid', ['track_id', 'puid'], unique=False)
    op.drop_index('track_meta_idx_uniq', table_name='track_meta')
    op.create_index('track_meta_idx_uniq', 'track_meta', ['track_id', 'meta_id'], unique=False)
    op.drop_index('track_mbid_idx_uniq', table_name='track_mbid')
    op.create_index('track_mbid_idx_uniq', 'track_mbid', ['track_id', 'mbid'], unique=False)
    op.drop_index('track_foreignid_idx_uniq', table_name='track_foreignid')
    op.create_index('track_foreignid_idx_uniq', 'track_foreignid', ['track_id', 'foreignid_id'], unique=False)
    op.drop_constraint(op.f('stats_user_agents_fk_application_id'), 'stats_user_agents', type_='foreignkey')
    op.drop_constraint(op.f('stats_lookups_fk_application_id'), 'stats_lookups', type_='foreignkey')
    op.drop_constraint(op.f('application_fk_account_id'), 'application', type_='foreignkey')
    op.drop_constraint(op.f('account_google_fk_account_id'), 'account_google', type_='foreignkey')
