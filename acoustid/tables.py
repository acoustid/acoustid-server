import sqlalchemy.event
from sqlalchemy import (
    MetaData, Table, Column, Index,
    ForeignKey, CheckConstraint,
    Integer, String, DateTime, Boolean, Date, Text, SmallInteger, BigInteger, CHAR,
    DDL, event, sql,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID, INET

metadata = MetaData(naming_convention={
    'fk': '%(table_name)s_fk_%(column_0_name)s',
    'ix': '%(table_name)s_idx_%(column_0_name)s',
    'pk': '%(table_name)s_pkey',
})

import mbdata.config
mbdata.config.configure(metadata=metadata, schema='musicbrainz')

sqlalchemy.event.listen(
    metadata, 'before_create',
    DDL('CREATE SCHEMA IF NOT EXISTS musicbrainz'),
)

def create_replication_control_table(name):
    return Table(name, metadata,
        Column('id', Integer, primary_key=True),
        Column('current_schema_sequence', Integer, nullable=False),
        Column('current_replication_sequence', Integer),
        Column('last_replication_date', DateTime(timezone=True)),
    )

replication_control = create_replication_control_table('replication_control')
acoustid_mb_replication_control = create_replication_control_table('acoustid_mb_replication_control')

account = Table('account', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String, nullable=False),
    Column('apikey', String, nullable=False),
    Column('mbuser', String),
    Column('anonymous', Boolean, default=False, server_default=sql.false()),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('lastlogin', DateTime(timezone=True)),
    Column('submission_count', Integer, nullable=False, server_default=sql.literal(0)),
    Column('application_id', Integer, ForeignKey('application.id')),
    Column('application_version', String),
    Column('created_from', INET),
    Column('is_admin', Boolean, default=False, server_default=sql.false(), nullable=False),
    Index('account_idx_mbuser', 'mbuser', unique=True),
    Index('account_idx_apikey', 'apikey', unique=True),
)

account_stats_control = Table('account_stats_control', metadata,
    Column('id', Integer, primary_key=True),
    Column('last_updated', DateTime(timezone=True), nullable=False),
)

account_openid = Table('account_openid', metadata,
    Column('openid', String, primary_key=True),
    Column('account_id', Integer, ForeignKey('account.id'), nullable=False),
    Index('account_openid_idx_account_id', 'account_id'),
)

account_google = Table('account_google', metadata,
    Column('google_user_id', String, primary_key=True),
    Column('account_id', Integer, ForeignKey('account.id'), nullable=False),
    Index('account_google_idx_account_id', 'account_id'),
)

application = Table('application', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String, nullable=False),
    Column('version', String, nullable=False),
    Column('apikey', String, nullable=False),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('active', Boolean, default=True, server_default=sql.true()),
    Column('account_id', Integer, ForeignKey('account.id'), nullable=False),
    Column('email', String),
    Column('website', String),
    Index('application_idx_apikey', 'apikey', unique=True),
)

track = Table('track', metadata,
    Column('id', Integer, primary_key=True),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('new_id', Integer, ForeignKey('track.id')),
    Column('gid', UUID, nullable=False),
    Index('track_idx_gid', 'gid', unique=True),
)

format = Table('format', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String, nullable=False),
    Index('format_idx_name', 'name', unique=True),
)

source = Table('source', metadata,
    Column('id', Integer, primary_key=True),
    Column('application_id', Integer, ForeignKey('application.id'), nullable=False),
    Column('account_id', Integer, ForeignKey('account.id'), nullable=False),
    Column('version', String),
    Index('source_idx_uniq', 'application_id', 'account_id', 'version', unique=True),
)

submission = Table('submission', metadata,
    Column('id', Integer, primary_key=True),
    Column('fingerprint', ARRAY(Integer), nullable=False),
    Column('length', SmallInteger, CheckConstraint('length>0'), nullable=False),
    Column('bitrate', SmallInteger, CheckConstraint('bitrate>0')),
    Column('format_id', Integer, ForeignKey('format.id')),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('source_id', Integer, ForeignKey('source.id'), nullable=False),
    Column('mbid', UUID),
    Column('handled', Boolean, default=False, server_default=sql.false()),
    Column('puid', UUID),
    Column('meta_id', Integer, ForeignKey('meta.id')),
    Column('foreignid_id', Integer, ForeignKey('foreignid.id')),
)

Index('submission_idx_handled', submission.c.id, postgresql_where=submission.c.handled == False)

stats = Table('stats', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String, nullable=False),
    Column('date', Date, server_default=sql.func.current_date(), nullable=False),
    Column('value', Integer, nullable=False),
    Index('stats_idx_date', 'date'),
    Index('stats_idx_name_date', 'name', 'date'),
)

stats_lookups = Table('stats_lookups', metadata,
    Column('id', Integer, primary_key=True),
    Column('date', Date, nullable=False),
    Column('hour', Integer, nullable=False),
    Column('application_id', Integer, ForeignKey('application.id'), nullable=False),
    Column('count_nohits', Integer, default=0, server_default=sql.literal(0), nullable=False),
    Column('count_hits', Integer, default=0, server_default=sql.literal(0), nullable=False),
    Index('stats_lookups_idx_date', 'date'),
)

stats_user_agents = Table('stats_user_agents', metadata,
    Column('id', Integer, primary_key=True),
    Column('date', Date, nullable=False),
    Column('application_id', Integer, ForeignKey('application.id'), nullable=False),
    Column('user_agent', String, nullable=False),
    Column('ip', String, nullable=False),
    Column('count', Integer, default=0, server_default=sql.literal(0), nullable=False),
    Index('stats_user_agents_idx_date', 'date'),
)

stats_top_accounts = Table('stats_top_accounts', metadata,
    Column('id', Integer, primary_key=True),
    Column('account_id', Integer, ForeignKey('account.id'), nullable=False),
    Column('count', Integer, nullable=False),
)

meta = Table('meta', metadata,
    Column('id', Integer, primary_key=True),
    Column('track', String),
    Column('artist', String),
    Column('album', String),
    Column('album_artist', String),
    Column('track_no', Integer),
    Column('disc_no', Integer),
    Column('year', Integer),
)

foreignid_vendor = Table('foreignid_vendor', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String, nullable=False),
    Index('foreignid_vendor_idx_name', 'name', unique=True),
)

foreignid = Table('foreignid', metadata,
    Column('id', Integer, primary_key=True),
    Column('vendor_id', Integer, ForeignKey('foreignid_vendor.id'), nullable=False),
    Column('name', Text, nullable=False),
    Index('foreignid_idx_vendor', 'vendor_id'),
    Index('foreignid_idx_vendor_name', 'vendor_id', 'name', unique=True),
)

fingerprint = Table('fingerprint', metadata,
    Column('id', Integer, primary_key=True),
    Column('fingerprint', ARRAY(Integer), nullable=False),
    Column('length', SmallInteger, CheckConstraint('length>0'), nullable=False),
    Column('bitrate', SmallInteger, CheckConstraint('bitrate>0')),
    Column('format_id', Integer, ForeignKey('format.id')),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('track_id', Integer, ForeignKey('track.id'), nullable=False),
    Column('submission_count', Integer, nullable=False),
    Index('fingerprint_idx_length', 'length'),
    Index('fingerprint_idx_track_id', 'track_id'),
)

fingerprint_source = Table('fingerprint_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('fingerprint_id', Integer, ForeignKey('fingerprint.id'), nullable=False),
    Column('submission_id', Integer, nullable=False),
    Column('source_id', Integer, ForeignKey('source.id'), nullable=False),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Index('fingerprint_source_idx_submission_id', 'submission_id'),
)

fingerprint_index_queue = Table('fingerprint_index_queue', metadata,
    Column('fingerprint_id', Integer, nullable=False),
)

track_mbid = Table('track_mbid', metadata,
    Column('track_id', Integer, ForeignKey('track.id'), nullable=False),
    Column('mbid', UUID, nullable=False, index=True),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('id', Integer, primary_key=True),
    Column('submission_count', Integer, nullable=False),
    Column('disabled', Boolean, default=False, server_default=sql.false(), nullable=False),
    Index('track_mbid_idx_uniq', 'track_id', 'mbid', unique=True),
)

track_mbid_source = Table('track_mbid_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_mbid_id', Integer, ForeignKey('track_mbid.id'), nullable=False, index=True),
    Column('submission_id', Integer),
    Column('source_id', Integer, ForeignKey('source.id'), nullable=False, index=True),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
)

track_mbid_change = Table('track_mbid_change', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_mbid_id', Integer, ForeignKey('track_mbid.id'), nullable=False, index=True),
    Column('account_id', Integer, ForeignKey('account.id'), nullable=False),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('disabled', Boolean, nullable=False),
    Column('note', Text),
)

track_mbid_flag = Table('track_mbid_flag', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_mbid_id', Integer, ForeignKey('track_mbid.id'), nullable=False),
    Column('account_id', Integer, ForeignKey('account.id'), nullable=False),
    Column('handled', Boolean, default=False, server_default=sql.false(), nullable=False),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
)

track_puid = Table('track_puid', metadata,
    Column('track_id', Integer, ForeignKey('track.id'), nullable=False),
    Column('puid', UUID, nullable=False, index=True),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('id', Integer, primary_key=True),
    Column('submission_count', Integer, nullable=False),
    Index('track_puid_idx_uniq', 'track_id', 'puid', unique=True),
)

track_puid_source = Table('track_puid_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_puid_id', Integer, ForeignKey('track_puid.id'), nullable=False),
    Column('submission_id', Integer, nullable=False),
    Column('source_id', Integer, ForeignKey('source.id'), nullable=False),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
)

track_meta = Table('track_meta', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_id', Integer, ForeignKey('track.id'), nullable=False),
    Column('meta_id', Integer, ForeignKey('meta.id'), nullable=False, index=True),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('submission_count', Integer, nullable=False),
    Index('track_meta_idx_uniq', 'track_id', 'meta_id', unique=True),
)

track_meta_source = Table('track_meta_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_meta_id', Integer, ForeignKey('track_meta.id'), nullable=False),
    Column('submission_id', Integer, nullable=False),
    Column('source_id', Integer, ForeignKey('source.id'), nullable=False),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
)

track_foreignid = Table('track_foreignid', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_id', Integer, ForeignKey('track.id'), nullable=False),
    Column('foreignid_id', Integer, ForeignKey('foreignid.id'), nullable=False, index=True),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('submission_count', Integer, nullable=False),
    Index('track_foreignid_idx_uniq', 'track_id', 'foreignid_id', unique=True),
)

track_foreignid_source = Table('track_foreignid_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_foreignid_id', Integer, ForeignKey('track_foreignid.id'), nullable=False),
    Column('submission_id', Integer, nullable=False),
    Column('source_id', Integer, ForeignKey('source.id'), nullable=False),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
)

recording_acoustid = Table('recording_acoustid', metadata,
    Column('id', Integer, primary_key=True, autoincrement=False),
    Column('acoustid', UUID, nullable=False, index=True),
    Column('recording', UUID, nullable=False),
    Column('disabled', Boolean, default=False, server_default=sql.false(), nullable=False),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('updated', DateTime(timezone=True)),
    Index('recording_acoustid_idx_uniq', 'recording', 'acoustid', unique=True),
)

mirror_queue = Table('mirror_queue', metadata,
    Column('id', Integer, primary_key=True),
    Column('txid', BigInteger, nullable=False, server_default=sql.func.txid_current()),
    Column('tblname', String, nullable=False),
    Column('op', CHAR(1), CheckConstraint("op = ANY (ARRAY['I'::bpchar, 'U'::bpchar, 'D'::bpchar])"), nullable=False),
    Column('data', Text, nullable=False),
)

import mbdata.models
mb_area = mbdata.models.Area.__table__
mb_artist_credit = mbdata.models.ArtistCredit.__table__
mb_artist_credit_name = mbdata.models.ArtistCreditName.__table__
mb_artist = mbdata.models.Artist.__table__
mb_iso_3166_1 = mbdata.models.ISO31661.__table__
mb_medium_format = mbdata.models.MediumFormat.__table__
mb_medium = mbdata.models.Medium.__table__
mb_recording_gid_redirect = mbdata.models.RecordingGIDRedirect.__table__
mb_recording = mbdata.models.Recording.__table__
mb_release_group = mbdata.models.ReleaseGroup.__table__
mb_release_group_primary_type = mbdata.models.ReleaseGroupPrimaryType.__table__
mb_release_group_secondary_type_join = mbdata.models.ReleaseGroupSecondaryTypeJoin.__table__
mb_release_group_secondary_type = mbdata.models.ReleaseGroupSecondaryType.__table__
mb_release = mbdata.models.Release.__table__
mb_track = mbdata.models.Track.__table__

# XXX either stop using this or define view models in mbdata
mb_release_country = Table('release_event', metadata,
    Column('release', Integer, ForeignKey('musicbrainz.release.id')),
    Column('country', Integer, ForeignKey('musicbrainz.area.id')),
    Column('date_year', Integer),
    Column('date_month', Integer),
    Column('date_day', Integer),
    schema='musicbrainz',
)
