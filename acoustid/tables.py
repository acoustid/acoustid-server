import sqlalchemy.event
from sqlalchemy import (
    MetaData, Table, Column, Index,
    ForeignKey, CheckConstraint,
    Integer, String, DateTime, Boolean, Date, Text, SmallInteger,
    DDL, sql,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID, INET, JSONB

metadata = MetaData(naming_convention={
    'fk': '%(table_name)s_fk_%(column_0_name)s',
    'ix': '%(table_name)s_idx_%(column_0_name)s',
    'pk': '%(table_name)s_pkey',
})

import mbdata.config  # noqa: E402
mbdata.config.configure(metadata=metadata, schema='musicbrainz')

sqlalchemy.event.listen(
    metadata, 'before_create',
    DDL('CREATE SCHEMA IF NOT EXISTS musicbrainz'),
)

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
    info={'bind_key': 'app'},
)

account_openid = Table('account_openid', metadata,
    Column('openid', String, primary_key=True),
    Column('account_id', Integer, ForeignKey('account.id'), nullable=False),
    Index('account_openid_idx_account_id', 'account_id'),
    info={'bind_key': 'app'},
)

account_google = Table('account_google', metadata,
    Column('google_user_id', String, primary_key=True),
    Column('account_id', Integer, ForeignKey('account.id'), nullable=False),
    Index('account_google_idx_account_id', 'account_id'),
    info={'bind_key': 'app'},
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
    info={'bind_key': 'app'},
)

track = Table('track', metadata,
    Column('id', Integer, primary_key=True),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('new_id', Integer, ForeignKey('track.id')),
    Column('gid', UUID, nullable=False),
    Index('track_idx_gid', 'gid', unique=True),
    info={'bind_key': 'fingerprint'},
)

format = Table('format', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String, nullable=False),
    Index('format_idx_name', 'name', unique=True),
    info={'bind_key': 'app'},
)

source = Table('source', metadata,
    Column('id', Integer, primary_key=True),
    Column('application_id', Integer, ForeignKey('application.id'), nullable=False),
    Column('account_id', Integer, ForeignKey('account.id'), nullable=False),
    Column('version', String),
    Index('source_idx_uniq', 'application_id', 'account_id', 'version', unique=True),
    info={'bind_key': 'app'},
)

submission = Table('submission', metadata,
    Column('id', Integer, primary_key=True),

    # status
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('handled_at', DateTime(timezone=True)),
    Column('handled', Boolean, default=False, server_default=sql.false()),

    # source
    Column('account_id', Integer, nullable=True),
    Column('application_id', Integer, nullable=True),
    Column('application_version', String),
    Column('source_id', Integer, nullable=True),  # XXX deprecated

    # fingerprint
    Column('fingerprint', ARRAY(Integer), nullable=False),
    Column('length', SmallInteger, CheckConstraint('length>0'), nullable=False),
    Column('bitrate', SmallInteger, CheckConstraint('bitrate>0')),
    Column('format', String),
    Column('format_id', Integer),  # XXX deprecated

    # metadata
    Column('meta', JSONB),
    Column('meta_id', Integer),  # XXX deprecated
    Column('mbid', UUID),
    Column('puid', UUID),
    Column('foreignid', String),
    Column('foreignid_id', Integer),  # XXX deprecated

    info={'bind_key': 'ingest'},
)

Index('submission_idx_handled', submission.c.id, postgresql_where=submission.c.handled == False)  # noqa: E712

submission_result = Table('submission_result', metadata,
    Column('submission_id', Integer, primary_key=True, autoincrement=False),

    # status
    Column('created', DateTime(timezone=True), nullable=False),
    Column('handled_at', DateTime(timezone=True), nullable=True),

    # source
    Column('account_id', Integer, nullable=False),
    Column('application_id', Integer, nullable=False),
    Column('application_version', String),

    # fingerprint
    Column('fingerprint_id', Integer, nullable=False),
    Column('track_id', Integer, nullable=False),

    # metadata
    Column('meta_id', Integer),
    Column('mbid', UUID),
    Column('puid', UUID),
    Column('foreignid', String),

    info={'bind_key': 'ingest'},
)

stats = Table('stats', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String, nullable=False),
    Column('date', Date, server_default=sql.func.current_date(), nullable=False),
    Column('value', Integer, nullable=False),
    Index('stats_idx_date', 'date'),
    Index('stats_idx_name_date', 'name', 'date'),
    info={'bind_key': 'app'},
)

stats_lookups = Table('stats_lookups', metadata,
    Column('id', Integer, primary_key=True),
    Column('date', Date, nullable=False),
    Column('hour', Integer, nullable=False),
    Column('application_id', Integer, ForeignKey('application.id'), nullable=False),
    Column('count_nohits', Integer, default=0, server_default=sql.literal(0), nullable=False),
    Column('count_hits', Integer, default=0, server_default=sql.literal(0), nullable=False),
    Index('stats_lookups_idx_date', 'date'),
    info={'bind_key': 'app'},
)

stats_user_agents = Table('stats_user_agents', metadata,
    Column('id', Integer, primary_key=True),
    Column('date', Date, nullable=False),
    Column('application_id', Integer, ForeignKey('application.id'), nullable=False),
    Column('user_agent', String, nullable=False),
    Column('ip', String, nullable=False),
    Column('count', Integer, default=0, server_default=sql.literal(0), nullable=False),
    Index('stats_user_agents_idx_date', 'date'),
    info={'bind_key': 'app'},
)

stats_top_accounts = Table('stats_top_accounts', metadata,
    Column('id', Integer, primary_key=True),
    Column('account_id', Integer, ForeignKey('account.id'), nullable=False),
    Column('count', Integer, nullable=False),
    info={'bind_key': 'app'},
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
    # Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('created', DateTime(timezone=True)),
    info={'bind_key': 'fingerprint'},
)

foreignid_vendor = Table('foreignid_vendor', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String, nullable=False),
    Index('foreignid_vendor_idx_name', 'name', unique=True),
    info={'bind_key': 'fingerprint'},
)

foreignid = Table('foreignid', metadata,
    Column('id', Integer, primary_key=True),
    Column('vendor_id', Integer, ForeignKey('foreignid_vendor.id'), nullable=False),
    Column('name', Text, nullable=False),
    Index('foreignid_idx_vendor', 'vendor_id'),
    Index('foreignid_idx_vendor_name', 'vendor_id', 'name', unique=True),
    info={'bind_key': 'fingerprint'},
)

foreignid.add_is_dependent_on(foreignid_vendor)

fingerprint = Table('fingerprint', metadata,
    Column('id', Integer, primary_key=True),
    Column('fingerprint', ARRAY(Integer), nullable=False),
    Column('length', SmallInteger, CheckConstraint('length>0'), nullable=False),
    Column('bitrate', SmallInteger, CheckConstraint('bitrate>0')),
    Column('format_id', Integer),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('track_id', Integer, ForeignKey('track.id'), nullable=False),
    Column('submission_count', Integer, nullable=False),
    Index('fingerprint_idx_length', 'length'),
    Index('fingerprint_idx_track_id', 'track_id'),
    info={'bind_key': 'fingerprint'},
)

fingerprint_source = Table('fingerprint_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('fingerprint_id', Integer, nullable=False),
    Column('submission_id', Integer, nullable=False),
    Column('source_id', Integer, nullable=False),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Index('fingerprint_source_idx_submission_id', 'submission_id'),
    info={'bind_key': 'ingest'},
)

track_mbid = Table('track_mbid', metadata,
    Column('track_id', Integer, ForeignKey('track.id'), nullable=False),
    Column('mbid', UUID, nullable=False, index=True),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('id', Integer, primary_key=True),
    Column('submission_count', Integer, nullable=False),
    Column('disabled', Boolean, default=False, server_default=sql.false(), nullable=False),
    Index('track_mbid_idx_uniq', 'track_id', 'mbid', unique=True),
    info={'bind_key': 'fingerprint'},
)

track_mbid_source = Table('track_mbid_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_mbid_id', Integer, nullable=False, index=True),
    Column('submission_id', Integer),
    Column('source_id', Integer, nullable=False, index=True),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    info={'bind_key': 'ingest'},
)

track_mbid_change = Table('track_mbid_change', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_mbid_id', Integer, nullable=False, index=True),
    Column('account_id', Integer, nullable=False),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('disabled', Boolean, nullable=False),
    Column('note', Text),
    info={'bind_key': 'ingest'},
)

track_puid = Table('track_puid', metadata,
    Column('track_id', Integer, ForeignKey('track.id'), nullable=False),
    Column('puid', UUID, nullable=False, index=True),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('id', Integer, primary_key=True),
    Column('submission_count', Integer, nullable=False),
    Index('track_puid_idx_uniq', 'track_id', 'puid', unique=True),
    info={'bind_key': 'fingerprint'},
)

track_puid_source = Table('track_puid_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_puid_id', Integer, nullable=False),
    Column('submission_id', Integer, nullable=False),
    Column('source_id', Integer, nullable=False),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    info={'bind_key': 'ingest'},
)

track_meta = Table('track_meta', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_id', Integer, ForeignKey('track.id'), nullable=False),
    Column('meta_id', Integer, ForeignKey('meta.id'), nullable=False, index=True),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('submission_count', Integer, nullable=False),
    Index('track_meta_idx_uniq', 'track_id', 'meta_id', unique=True),
    info={'bind_key': 'fingerprint'},
)

track_meta_source = Table('track_meta_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_meta_id', Integer, nullable=False),
    Column('submission_id', Integer, nullable=False),
    Column('source_id', Integer, nullable=False),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    info={'bind_key': 'ingest'},
)

track_foreignid = Table('track_foreignid', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_id', Integer, ForeignKey('track.id'), nullable=False),
    Column('foreignid_id', Integer, ForeignKey('foreignid.id'), nullable=False, index=True),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    Column('submission_count', Integer, nullable=False),
    Index('track_foreignid_idx_uniq', 'track_id', 'foreignid_id', unique=True),
    info={'bind_key': 'fingerprint'},
)

track_foreignid_source = Table('track_foreignid_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_foreignid_id', Integer, nullable=False),
    Column('submission_id', Integer, nullable=False),
    Column('source_id', Integer, nullable=False),
    Column('created', DateTime(timezone=True), server_default=sql.func.current_timestamp(), nullable=False),
    info={'bind_key': 'ingest'},
)

import mbdata.models  # noqa: E402
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
    info={'bind_key': 'musicbrainz'},
)

for table in metadata.sorted_tables:
    if table.schema in {'musicbrainz', 'cover_art_archive', 'event_art_archive', 'wikidocs', 'statistics', 'documentation'}:
        table.info['bind_key'] = 'musicbrainz'  # type: ignore
