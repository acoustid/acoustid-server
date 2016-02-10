"""initial

Revision ID: 57c4d22c87b8
Revises: 
Create Date: 2016-02-10 21:12:42.367918

"""

# revision identifiers, used by Alembic.
revision = '57c4d22c87b8'
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table('account_google',
        sa.Column('google_user_id', sa.String(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('google_user_id')
    )
    op.create_index('account_google_idx_account_id', 'account_google', ['account_id'], unique=False)
    op.create_table('account_stats_control',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('acoustid_mb_replication_control',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('current_schema_sequence', sa.Integer(), nullable=False),
        sa.Column('current_replication_sequence', sa.Integer(), nullable=True),
        sa.Column('last_replication_date', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('application',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('apikey', sa.String(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('active', sa.Boolean(), server_default=sa.text(u'true'), nullable=True),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('website', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('application_idx_apikey', 'application', ['apikey'], unique=True)
    op.create_table('fingerprint_index_queue',
        sa.Column('fingerprint_id', sa.Integer(), nullable=False)
    )
    op.create_table('foreignid_vendor',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('foreignid_vendor_idx_name', 'foreignid_vendor', ['name'], unique=True)
    op.create_table('format',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('format_idx_name', 'format', ['name'], unique=True)
    op.create_table('meta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('track', sa.String(), nullable=True),
        sa.Column('artist', sa.String(), nullable=True),
        sa.Column('album', sa.String(), nullable=True),
        sa.Column('album_artist', sa.String(), nullable=True),
        sa.Column('track_no', sa.Integer(), nullable=True),
        sa.Column('disc_no', sa.Integer(), nullable=True),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mirror_queue',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('txid', sa.BigInteger(), server_default=sa.text(u'txid_current()'), nullable=False),
        sa.Column('tblname', sa.String(), nullable=False),
        sa.Column('op', sa.CHAR(length=1), nullable=False),
        sa.Column('data', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('recording_acoustid',
        sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('acoustid', postgresql.UUID(), nullable=False),
        sa.Column('recording', postgresql.UUID(), nullable=False),
        sa.Column('disabled', sa.Boolean(), server_default=sa.text(u'false'), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('updated', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('recording_acoustid_idx_acoustid'), 'recording_acoustid', ['acoustid'], unique=False)
    op.create_index('recording_acoustid_idx_uniq', 'recording_acoustid', ['recording', 'acoustid'], unique=True)
    op.create_table('replication_control',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('current_schema_sequence', sa.Integer(), nullable=False),
        sa.Column('current_replication_sequence', sa.Integer(), nullable=True),
        sa.Column('last_replication_date', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('stats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('date', sa.Date(), server_default=sa.text(u'CURRENT_DATE'), nullable=False),
        sa.Column('value', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('stats_idx_date', 'stats', ['date'], unique=False)
    op.create_index('stats_idx_name_date', 'stats', ['name', 'date'], unique=False)
    op.create_table('stats_lookups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('hour', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('count_nohits', sa.Integer(), server_default=sa.text(u'0'), nullable=False),
        sa.Column('count_hits', sa.Integer(), server_default=sa.text(u'0'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('stats_lookups_idx_date', 'stats_lookups', ['date'], unique=False)
    op.create_table('stats_user_agents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('user_agent', sa.String(), nullable=False),
        sa.Column('ip', sa.String(), nullable=False),
        sa.Column('count', sa.Integer(), server_default=sa.text(u'0'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('stats_user_agents_idx_date', 'stats_user_agents', ['date'], unique=False)
    op.create_table('track',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('new_id', sa.Integer(), nullable=True),
        sa.Column('gid', postgresql.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['new_id'], ['track.id'], name=op.f('track_fk_new_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('track_idx_gid', 'track', ['gid'], unique=True)
    op.create_table('account',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('apikey', sa.String(), nullable=False),
        sa.Column('mbuser', sa.String(), nullable=True),
        sa.Column('anonymous', sa.Boolean(), server_default=sa.text(u'false'), nullable=True),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('lastlogin', sa.DateTime(timezone=True), nullable=True),
        sa.Column('submission_count', sa.Integer(), server_default=sa.text(u'0'), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=True),
        sa.Column('application_version', sa.String(), nullable=True),
        sa.Column('created_from', postgresql.INET(), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['application.id'], name=op.f('account_fk_application_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('account_idx_apikey', 'account', ['apikey'], unique=True)
    op.create_index('account_idx_mbuser', 'account', ['mbuser'], unique=True)
    op.create_table('fingerprint',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fingerprint', postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column('length', sa.SmallInteger(), nullable=False),
        sa.Column('bitrate', sa.SmallInteger(), nullable=True),
        sa.Column('format_id', sa.Integer(), nullable=True),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=False),
        sa.Column('submission_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['format_id'], ['format.id'], name=op.f('fingerprint_fk_format_id')),
        sa.ForeignKeyConstraint(['track_id'], ['track.id'], name=op.f('fingerprint_fk_track_id')),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('length > 0', name=op.f('fingerprint_length_check')),
        sa.CheckConstraint('bitrate > 0', name=op.f('fingerprint_bitrate_check')),
    )
    op.create_index('fingerprint_idx_length', 'fingerprint', ['length'], unique=False)
    op.create_index('fingerprint_idx_track_id', 'fingerprint', ['track_id'], unique=False)
    op.create_table('foreignid',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('vendor_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['vendor_id'], ['foreignid_vendor.id'], name=op.f('foreignid_fk_vendor_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('foreignid_idx_vendor', 'foreignid', ['vendor_id'], unique=False)
    op.create_index('foreignid_idx_vendor_name', 'foreignid', ['vendor_id', 'name'], unique=True)
    op.create_table('track_mbid',
        sa.Column('track_id', sa.Integer(), nullable=False),
        sa.Column('mbid', postgresql.UUID(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('submission_count', sa.Integer(), nullable=False),
        sa.Column('disabled', sa.Boolean(), server_default=sa.text(u'false'), nullable=False),
        sa.ForeignKeyConstraint(['track_id'], ['track.id'], name=op.f('track_mbid_fk_track_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('track_mbid_idx_mbid'), 'track_mbid', ['mbid'], unique=False)
    op.create_index('track_mbid_idx_uniq', 'track_mbid', ['track_id', 'mbid'], unique=False)
    op.create_table('track_meta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=False),
        sa.Column('meta_id', sa.Integer(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('submission_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['meta_id'], ['meta.id'], name=op.f('track_meta_fk_meta_id')),
        sa.ForeignKeyConstraint(['track_id'], ['track.id'], name=op.f('track_meta_fk_track_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('track_meta_idx_meta_id'), 'track_meta', ['meta_id'], unique=False)
    op.create_index('track_meta_idx_uniq', 'track_meta', ['track_id', 'meta_id'], unique=False)
    op.create_table('track_puid',
        sa.Column('track_id', sa.Integer(), nullable=False),
        sa.Column('puid', postgresql.UUID(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('submission_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['track_id'], ['track.id'], name=op.f('track_puid_fk_track_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('track_puid_idx_puid'), 'track_puid', ['puid'], unique=False)
    op.create_index('track_puid_idx_uniq', 'track_puid', ['track_id', 'puid'], unique=False)
    op.create_table('account_openid',
        sa.Column('openid', sa.String(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['account.id'], name=op.f('account_openid_fk_account_id')),
        sa.PrimaryKeyConstraint('openid')
    )
    op.create_index('account_openid_idx_account_id', 'account_openid', ['account_id'], unique=False)
    op.create_table('source',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['account.id'], name=op.f('source_fk_account_id')),
        sa.ForeignKeyConstraint(['application_id'], ['application.id'], name=op.f('source_fk_application_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('source_idx_uniq', 'source', ['application_id', 'account_id', 'version'], unique=True)
    op.create_table('stats_top_accounts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['account.id'], name=op.f('stats_top_accounts_fk_account_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('track_foreignid',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('track_id', sa.Integer(), nullable=False),
        sa.Column('foreignid_id', sa.Integer(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('submission_count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['foreignid_id'], ['foreignid.id'], name=op.f('track_foreignid_fk_foreignid_id')),
        sa.ForeignKeyConstraint(['track_id'], ['track.id'], name=op.f('track_foreignid_fk_track_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('track_foreignid_idx_foreignid_id'), 'track_foreignid', ['foreignid_id'], unique=False)
    op.create_index('track_foreignid_idx_uniq', 'track_foreignid', ['track_id', 'foreignid_id'], unique=False)
    op.create_table('track_mbid_change',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('track_mbid_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('disabled', sa.Boolean(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['account.id'], name=op.f('track_mbid_change_fk_account_id')),
        sa.ForeignKeyConstraint(['track_mbid_id'], ['track_mbid.id'], name=op.f('track_mbid_change_fk_track_mbid_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('track_mbid_change_idx_track_mbid_id'), 'track_mbid_change', ['track_mbid_id'], unique=False)
    op.create_table('track_mbid_flag',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('track_mbid_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('handled', sa.Boolean(), server_default=sa.text(u'false'), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['account.id'], name=op.f('track_mbid_flag_fk_account_id')),
        sa.ForeignKeyConstraint(['track_mbid_id'], ['track_mbid.id'], name=op.f('track_mbid_flag_fk_track_mbid_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('submission',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fingerprint', postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column('length', sa.SmallInteger(), nullable=False),
        sa.Column('bitrate', sa.SmallInteger(), nullable=True),
        sa.Column('format_id', sa.Integer(), nullable=True),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('mbid', postgresql.UUID(), nullable=True),
        sa.Column('handled', sa.Boolean(), server_default=sa.text(u'false'), nullable=True),
        sa.Column('puid', postgresql.UUID(), nullable=True),
        sa.Column('meta_id', sa.Integer(), nullable=True),
        sa.Column('foreignid_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['foreignid_id'], ['foreignid.id'], name=op.f('submission_fk_foreignid_id')),
        sa.ForeignKeyConstraint(['format_id'], ['format.id'], name=op.f('submission_fk_format_id')),
        sa.ForeignKeyConstraint(['meta_id'], ['meta.id'], name=op.f('submission_fk_meta_id')),
        sa.ForeignKeyConstraint(['source_id'], ['source.id'], name=op.f('submission_fk_source_id')),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('length > 0', name=op.f('submission_length_check')),
        sa.CheckConstraint('bitrate > 0', name=op.f('submission_bitrate_check')),
    )
    op.create_index('submission_idx_handled', 'submission', ['id'], unique=False, postgresql_where=sa.text(u'handled = false'))
    op.create_table('fingerprint_source',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fingerprint_id', sa.Integer(), nullable=False),
        sa.Column('submission_id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['fingerprint_id'], ['fingerprint.id'], name=op.f('fingerprint_source_fk_fingerprint_id')),
        sa.ForeignKeyConstraint(['source_id'], ['source.id'], name=op.f('fingerprint_source_fk_source_id')),
        sa.ForeignKeyConstraint(['submission_id'], ['submission.id'], name=op.f('fingerprint_source_fk_submission_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('fingerprint_source_idx_submission_id', 'fingerprint_source', ['submission_id'], unique=False)
    op.create_table('track_foreignid_source',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('track_foreignid_id', sa.Integer(), nullable=False),
        sa.Column('submission_id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['source_id'], ['source.id'], name=op.f('track_foreignid_source_fk_source_id')),
        sa.ForeignKeyConstraint(['submission_id'], ['submission.id'], name=op.f('track_foreignid_source_fk_submission_id')),
        sa.ForeignKeyConstraint(['track_foreignid_id'], ['track_foreignid.id'], name=op.f('track_foreignid_source_fk_track_foreignid_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('track_mbid_source',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('track_mbid_id', sa.Integer(), nullable=False),
        sa.Column('submission_id', sa.Integer(), nullable=True),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['source_id'], ['source.id'], name=op.f('track_mbid_source_fk_source_id')),
        sa.ForeignKeyConstraint(['submission_id'], ['submission.id'], name=op.f('track_mbid_source_fk_submission_id')),
        sa.ForeignKeyConstraint(['track_mbid_id'], ['track_mbid.id'], name=op.f('track_mbid_source_fk_track_mbid_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('track_mbid_source_idx_source_id'), 'track_mbid_source', ['source_id'], unique=False)
    op.create_index(op.f('track_mbid_source_idx_track_mbid_id'), 'track_mbid_source', ['track_mbid_id'], unique=False)
    op.create_table('track_meta_source',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('track_meta_id', sa.Integer(), nullable=False),
        sa.Column('submission_id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['source_id'], ['source.id'], name=op.f('track_meta_source_fk_source_id')),
        sa.ForeignKeyConstraint(['submission_id'], ['submission.id'], name=op.f('track_meta_source_fk_submission_id')),
        sa.ForeignKeyConstraint(['track_meta_id'], ['track_meta.id'], name=op.f('track_meta_source_fk_track_meta_id')),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('track_puid_source',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('track_puid_id', sa.Integer(), nullable=False),
        sa.Column('submission_id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text(u'CURRENT_TIMESTAMP'), nullable=True),
        sa.ForeignKeyConstraint(['source_id'], ['source.id'], name=op.f('track_puid_source_fk_source_id')),
        sa.ForeignKeyConstraint(['submission_id'], ['submission.id'], name=op.f('track_puid_source_fk_submission_id')),
        sa.ForeignKeyConstraint(['track_puid_id'], ['track_puid.id'], name=op.f('track_puid_source_fk_track_puid_id')),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('track_puid_source')
    op.drop_table('track_meta_source')
    op.drop_index(op.f('track_mbid_source_idx_track_mbid_id'), table_name='track_mbid_source')
    op.drop_index(op.f('track_mbid_source_idx_source_id'), table_name='track_mbid_source')
    op.drop_table('track_mbid_source')
    op.drop_table('track_foreignid_source')
    op.drop_index('fingerprint_source_idx_submission_id', table_name='fingerprint_source')
    op.drop_table('fingerprint_source')
    op.drop_index('submission_idx_handled', table_name='submission')
    op.drop_table('submission')
    op.drop_table('track_mbid_flag')
    op.drop_index(op.f('track_mbid_change_idx_track_mbid_id'), table_name='track_mbid_change')
    op.drop_table('track_mbid_change')
    op.drop_index('track_foreignid_idx_uniq', table_name='track_foreignid')
    op.drop_index(op.f('track_foreignid_idx_foreignid_id'), table_name='track_foreignid')
    op.drop_table('track_foreignid')
    op.drop_table('stats_top_accounts')
    op.drop_index('source_idx_uniq', table_name='source')
    op.drop_table('source')
    op.drop_index('account_openid_idx_account_id', table_name='account_openid')
    op.drop_table('account_openid')
    op.drop_index('track_puid_idx_uniq', table_name='track_puid')
    op.drop_index(op.f('track_puid_idx_puid'), table_name='track_puid')
    op.drop_table('track_puid')
    op.drop_index('track_meta_idx_uniq', table_name='track_meta')
    op.drop_index(op.f('track_meta_idx_meta_id'), table_name='track_meta')
    op.drop_table('track_meta')
    op.drop_index('track_mbid_idx_uniq', table_name='track_mbid')
    op.drop_index(op.f('track_mbid_idx_mbid'), table_name='track_mbid')
    op.drop_table('track_mbid')
    op.drop_index('foreignid_idx_vendor_name', table_name='foreignid')
    op.drop_index('foreignid_idx_vendor', table_name='foreignid')
    op.drop_table('foreignid')
    op.drop_index('fingerprint_idx_track_id', table_name='fingerprint')
    op.drop_index('fingerprint_idx_length', table_name='fingerprint')
    op.drop_table('fingerprint')
    op.drop_index('account_idx_mbuser', table_name='account')
    op.drop_index('account_idx_apikey', table_name='account')
    op.drop_table('account')
    op.drop_index('track_idx_gid', table_name='track')
    op.drop_table('track')
    op.drop_index('stats_user_agents_idx_date', table_name='stats_user_agents')
    op.drop_table('stats_user_agents')
    op.drop_index('stats_lookups_idx_date', table_name='stats_lookups')
    op.drop_table('stats_lookups')
    op.drop_index('stats_idx_name_date', table_name='stats')
    op.drop_index('stats_idx_date', table_name='stats')
    op.drop_table('stats')
    op.drop_table('replication_control')
    op.drop_index('recording_acoustid_idx_uniq', table_name='recording_acoustid')
    op.drop_index(op.f('recording_acoustid_idx_acoustid'), table_name='recording_acoustid')
    op.drop_table('recording_acoustid')
    op.drop_table('mirror_queue')
    op.drop_table('meta')
    op.drop_index('format_idx_name', table_name='format')
    op.drop_table('format')
    op.drop_index('foreignid_vendor_idx_name', table_name='foreignid_vendor')
    op.drop_table('foreignid_vendor')
    op.drop_table('fingerprint_index_queue')
    op.drop_index('application_idx_apikey', table_name='application')
    op.drop_table('application')
    op.drop_table('acoustid_mb_replication_control')
    op.drop_table('account_stats_control')
    op.drop_index('account_google_idx_account_id', table_name='account_google')
    op.drop_table('account_google')
