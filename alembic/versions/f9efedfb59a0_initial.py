"""initial

Revision ID: f9efedfb59a0
Revises: 
Create Date: 2019-11-14 11:27:46.399242

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f9efedfb59a0'
down_revision = None
branch_labels = None
depends_on = None


def upgrade(engine_name):
    globals()["upgrade_%s" % engine_name]()


def downgrade(engine_name):
    globals()["downgrade_%s" % engine_name]()


def upgrade_app():
    op.create_table('account',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('apikey', sa.String(), nullable=False),
        sa.Column('mbuser', sa.String(), nullable=True),
        sa.Column('anonymous', sa.Boolean(), server_default=sa.text('false'), nullable=True),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('lastlogin', sa.DateTime(timezone=True), nullable=True),
        sa.Column('submission_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=True),
        sa.Column('application_version', sa.String(), nullable=True),
        sa.Column('created_from', postgresql.INET(), nullable=True),
        sa.Column('is_admin', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('account_pkey'))
    )
    op.create_index('account_idx_apikey', 'account', ['apikey'], unique=True)
    op.create_index('account_idx_mbuser', 'account', ['mbuser'], unique=True)
    op.create_table('account_google',
        sa.Column('google_user_id', sa.String(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('google_user_id', name=op.f('account_google_pkey'))
    )
    op.create_index('account_google_idx_account_id', 'account_google', ['account_id'], unique=False)
    op.create_table('account_openid',
        sa.Column('openid', sa.String(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('openid', name=op.f('account_openid_pkey'))
    )
    op.create_index('account_openid_idx_account_id', 'account_openid', ['account_id'], unique=False)
    op.create_table('application',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('apikey', sa.String(), nullable=False),
        sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=True),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('website', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('application_pkey'))
    )
    op.create_index('application_idx_apikey', 'application', ['apikey'], unique=True)
    op.create_table('format',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('format_pkey'))
    )
    op.create_index('format_idx_name', 'format', ['name'], unique=True)
    op.create_table('source',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('source_pkey'))
    )
    op.create_index('source_idx_uniq', 'source', ['application_id', 'account_id', 'version'], unique=True)
    op.create_table('stats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('date', sa.Date(), server_default=sa.text('CURRENT_DATE'), nullable=False),
        sa.Column('value', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('stats_pkey'))
    )
    op.create_index('stats_idx_date', 'stats', ['date'], unique=False)
    op.create_index('stats_idx_name_date', 'stats', ['name', 'date'], unique=False)
    op.create_table('stats_lookups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('hour', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('count_nohits', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('count_hits', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('stats_lookups_pkey'))
    )
    op.create_index('stats_lookups_idx_date', 'stats_lookups', ['date'], unique=False)
    op.create_table('stats_top_accounts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('stats_top_accounts_pkey'))
    )
    op.create_table('stats_user_agents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('application_id', sa.Integer(), nullable=False),
    sa.Column('user_agent', sa.String(), nullable=False),
    sa.Column('ip', sa.String(), nullable=False),
    sa.Column('count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('stats_user_agents_pkey'))
    )
    op.create_index('stats_user_agents_idx_date', 'stats_user_agents', ['date'], unique=False)
    # ### end Alembic commands ###


def downgrade_app():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('stats_user_agents_idx_date', table_name='stats_user_agents')
    op.drop_table('stats_user_agents')
    op.drop_table('stats_top_accounts')
    op.drop_index('stats_lookups_idx_date', table_name='stats_lookups')
    op.drop_table('stats_lookups')
    op.drop_index('stats_idx_name_date', table_name='stats')
    op.drop_index('stats_idx_date', table_name='stats')
    op.drop_table('stats')
    op.drop_index('source_idx_uniq', table_name='source')
    op.drop_table('source')
    op.drop_index('format_idx_name', table_name='format')
    op.drop_table('format')
    op.drop_index('application_idx_apikey', table_name='application')
    op.drop_table('application')
    op.drop_index('account_openid_idx_account_id', table_name='account_openid')
    op.drop_table('account_openid')
    op.drop_index('account_google_idx_account_id', table_name='account_google')
    op.drop_table('account_google')
    op.drop_index('account_idx_mbuser', table_name='account')
    op.drop_index('account_idx_apikey', table_name='account')
    op.drop_table('account')
    # ### end Alembic commands ###


def upgrade_ingest():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('fingerprint_source',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fingerprint_id', sa.Integer(), nullable=False),
    sa.Column('submission_id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('fingerprint_source_pkey'))
    )
    op.create_index('fingerprint_source_idx_submission_id', 'fingerprint_source', ['submission_id'], unique=False)
    op.create_table('submission',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fingerprint', postgresql.ARRAY(sa.Integer()), nullable=False),
    sa.Column('length', sa.SmallInteger(), nullable=False),
    sa.Column('bitrate', sa.SmallInteger(), nullable=True),
    sa.Column('format_id', sa.Integer(), nullable=True),
    sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('mbid', postgresql.UUID(), nullable=True),
    sa.Column('handled', sa.Boolean(), server_default=sa.text('false'), nullable=True),
    sa.Column('puid', postgresql.UUID(), nullable=True),
    sa.Column('meta_id', sa.Integer(), nullable=True),
    sa.Column('foreignid_id', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('submission_pkey'))
    )
    op.create_index('submission_idx_handled', 'submission', ['id'], unique=False, postgresql_where=sa.text('handled = false'))
    op.create_table('submission_result',
    sa.Column('submission_id', sa.Integer(), autoincrement=False, nullable=False),
    sa.Column('created', sa.DateTime(timezone=True), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('application_id', sa.Integer(), nullable=False),
    sa.Column('application_version', sa.String(), nullable=True),
    sa.Column('fingerprint_id', sa.Integer(), nullable=False),
    sa.Column('track_id', sa.Integer(), nullable=False),
    sa.Column('meta_id', sa.Integer(), nullable=True),
    sa.Column('mbid', postgresql.UUID(), nullable=True),
    sa.Column('puid', postgresql.UUID(), nullable=True),
    sa.Column('foreignid', sa.String(), nullable=True),
    sa.PrimaryKeyConstraint('submission_id', name=op.f('submission_result_pkey'))
    )
    op.create_table('track_foreignid_source',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('track_foreignid_id', sa.Integer(), nullable=False),
    sa.Column('submission_id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('track_foreignid_source_pkey'))
    )
    op.create_table('track_mbid_change',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('track_mbid_id', sa.Integer(), nullable=False),
    sa.Column('account_id', sa.Integer(), nullable=False),
    sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('disabled', sa.Boolean(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('track_mbid_change_pkey'))
    )
    op.create_index(op.f('track_mbid_change_idx_track_mbid_id'), 'track_mbid_change', ['track_mbid_id'], unique=False)
    op.create_table('track_mbid_source',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('track_mbid_id', sa.Integer(), nullable=False),
    sa.Column('submission_id', sa.Integer(), nullable=True),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('track_mbid_source_pkey'))
    )
    op.create_index(op.f('track_mbid_source_idx_source_id'), 'track_mbid_source', ['source_id'], unique=False)
    op.create_index(op.f('track_mbid_source_idx_track_mbid_id'), 'track_mbid_source', ['track_mbid_id'], unique=False)
    op.create_table('track_meta_source',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('track_meta_id', sa.Integer(), nullable=False),
    sa.Column('submission_id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('track_meta_source_pkey'))
    )
    op.create_table('track_puid_source',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('track_puid_id', sa.Integer(), nullable=False),
    sa.Column('submission_id', sa.Integer(), nullable=False),
    sa.Column('source_id', sa.Integer(), nullable=False),
    sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('track_puid_source_pkey'))
    )
    # ### end Alembic commands ###


def downgrade_ingest():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('track_puid_source')
    op.drop_table('track_meta_source')
    op.drop_index(op.f('track_mbid_source_idx_track_mbid_id'), table_name='track_mbid_source')
    op.drop_index(op.f('track_mbid_source_idx_source_id'), table_name='track_mbid_source')
    op.drop_table('track_mbid_source')
    op.drop_index(op.f('track_mbid_change_idx_track_mbid_id'), table_name='track_mbid_change')
    op.drop_table('track_mbid_change')
    op.drop_table('track_foreignid_source')
    op.drop_table('submission_result')
    op.drop_index('submission_idx_handled', table_name='submission')
    op.drop_table('submission')
    op.drop_index('fingerprint_source_idx_submission_id', table_name='fingerprint_source')
    op.drop_table('fingerprint_source')
    # ### end Alembic commands ###


def upgrade_fingerprint():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('fingerprint',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('fingerprint', postgresql.ARRAY(sa.Integer()), nullable=False),
    sa.Column('length', sa.SmallInteger(), nullable=False),
    sa.Column('bitrate', sa.SmallInteger(), nullable=True),
    sa.Column('format_id', sa.Integer(), nullable=True),
    sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('track_id', sa.Integer(), nullable=False),
    sa.Column('submission_count', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('fingerprint_pkey'))
    )
    op.create_index('fingerprint_idx_length', 'fingerprint', ['length'], unique=False)
    op.create_index('fingerprint_idx_track_id', 'fingerprint', ['track_id'], unique=False)
    op.create_table('foreignid_vendor',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('foreignid_vendor_pkey'))
    )
    op.create_index('foreignid_vendor_idx_name', 'foreignid_vendor', ['name'], unique=True)
    op.create_table('meta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('track', sa.String(), nullable=True),
    sa.Column('artist', sa.String(), nullable=True),
    sa.Column('album', sa.String(), nullable=True),
    sa.Column('album_artist', sa.String(), nullable=True),
    sa.Column('track_no', sa.Integer(), nullable=True),
    sa.Column('disc_no', sa.Integer(), nullable=True),
    sa.Column('year', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('meta_pkey'))
    )
    op.create_table('track',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('new_id', sa.Integer(), nullable=True),
    sa.Column('gid', postgresql.UUID(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('track_pkey'))
    )
    op.create_index('track_idx_gid', 'track', ['gid'], unique=True)
    op.create_table('track_foreignid',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('track_id', sa.Integer(), nullable=False),
    sa.Column('foreignid_id', sa.Integer(), nullable=False),
    sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('submission_count', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('track_foreignid_pkey'))
    )
    op.create_index(op.f('track_foreignid_idx_foreignid_id'), 'track_foreignid', ['foreignid_id'], unique=False)
    op.create_index('track_foreignid_idx_uniq', 'track_foreignid', ['track_id', 'foreignid_id'], unique=True)
    op.create_table('track_mbid',
    sa.Column('track_id', sa.Integer(), nullable=False),
    sa.Column('mbid', postgresql.UUID(), nullable=False),
    sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('submission_count', sa.Integer(), nullable=False),
    sa.Column('disabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('track_mbid_pkey'))
    )
    op.create_index(op.f('track_mbid_idx_mbid'), 'track_mbid', ['mbid'], unique=False)
    op.create_index('track_mbid_idx_uniq', 'track_mbid', ['track_id', 'mbid'], unique=True)
    op.create_table('track_meta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('track_id', sa.Integer(), nullable=False),
    sa.Column('meta_id', sa.Integer(), nullable=False),
    sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('submission_count', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('track_meta_pkey'))
    )
    op.create_index(op.f('track_meta_idx_meta_id'), 'track_meta', ['meta_id'], unique=False)
    op.create_index('track_meta_idx_uniq', 'track_meta', ['track_id', 'meta_id'], unique=True)
    op.create_table('track_puid',
    sa.Column('track_id', sa.Integer(), nullable=False),
    sa.Column('puid', postgresql.UUID(), nullable=False),
    sa.Column('created', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('submission_count', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('track_puid_pkey'))
    )
    op.create_index(op.f('track_puid_idx_puid'), 'track_puid', ['puid'], unique=False)
    op.create_index('track_puid_idx_uniq', 'track_puid', ['track_id', 'puid'], unique=True)
    op.create_table('foreignid',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('vendor_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('foreignid_pkey'))
    )
    op.create_index('foreignid_idx_vendor', 'foreignid', ['vendor_id'], unique=False)
    op.create_index('foreignid_idx_vendor_name', 'foreignid', ['vendor_id', 'name'], unique=True)
    # ### end Alembic commands ###


def downgrade_fingerprint():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index('foreignid_idx_vendor_name', table_name='foreignid')
    op.drop_index('foreignid_idx_vendor', table_name='foreignid')
    op.drop_table('foreignid')
    op.drop_index('track_puid_idx_uniq', table_name='track_puid')
    op.drop_index(op.f('track_puid_idx_puid'), table_name='track_puid')
    op.drop_table('track_puid')
    op.drop_index('track_meta_idx_uniq', table_name='track_meta')
    op.drop_index(op.f('track_meta_idx_meta_id'), table_name='track_meta')
    op.drop_table('track_meta')
    op.drop_index('track_mbid_idx_uniq', table_name='track_mbid')
    op.drop_index(op.f('track_mbid_idx_mbid'), table_name='track_mbid')
    op.drop_table('track_mbid')
    op.drop_index('track_foreignid_idx_uniq', table_name='track_foreignid')
    op.drop_index(op.f('track_foreignid_idx_foreignid_id'), table_name='track_foreignid')
    op.drop_table('track_foreignid')
    op.drop_index('track_idx_gid', table_name='track')
    op.drop_table('track')
    op.drop_table('meta')
    op.drop_index('foreignid_vendor_idx_name', table_name='foreignid_vendor')
    op.drop_table('foreignid_vendor')
    op.drop_index('fingerprint_idx_track_id', table_name='fingerprint')
    op.drop_index('fingerprint_idx_length', table_name='fingerprint')
    op.drop_table('fingerprint')
    # ### end Alembic commands ###
