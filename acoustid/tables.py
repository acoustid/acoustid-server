from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Boolean, Date, Text, DDL, event
from sqlalchemy.dialects.postgresql import ARRAY, UUID

metadata = MetaData()

import mbdata.config
mbdata.config.metadata = metadata

import mbdata.utils
mbdata.utils.patch_model_schemas(mbdata.utils.SINGLE_MUSICBRAINZ_SCHEMA)

event.listen(metadata, 'before_create', DDL('CREATE SCHEMA IF NOT EXISTS musicbrainz'))


account = Table('account', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    Column('apikey', String),
    Column('mbuser', String),
    Column('created', DateTime),
    Column('lastlogin', DateTime),
    Column('anonymous', Boolean),
    Column('submission_count', Integer),
    Column('created_from', String),
    Column('application_id', Integer, ForeignKey('application.id')),
    Column('application_version', String),
)

account_openid = Table('account_openid', metadata,
    Column('account_id', Integer, ForeignKey('account.id'), primary_key=True),
    Column('openid', String, primary_key=True),
)

account_google = Table('account_google', metadata,
    Column('account_id', Integer, ForeignKey('account.id'), primary_key=True),
    Column('google_user_id', String, primary_key=True),
)

application = Table('application', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    Column('version', String),
    Column('apikey', String),
    Column('created', DateTime),
    Column('account_id', Integer),
    Column('email', String),
    Column('website', String),
)

track = Table('track', metadata,
    Column('id', Integer, primary_key=True),
    Column('gid', UUID),
    Column('created', DateTime),
    Column('new_id', Integer),
)

format = Table('format', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
)

source = Table('source', metadata,
    Column('id', Integer, primary_key=True),
    Column('account_id', Integer, ForeignKey('account.id')),
    Column('application_id', Integer, ForeignKey('application.id')),
    Column('version', String),
)

submission = Table('submission', metadata,
    Column('id', Integer, primary_key=True),
    Column('fingerprint', ARRAY(Integer)),
    Column('length', Integer),
    Column('bitrate', Integer),
    Column('mbid', String),
    Column('puid', String),
    Column('source_id', Integer, ForeignKey('source.id')),
    Column('format_id', Integer, ForeignKey('format.id')),
    Column('created', DateTime),
    Column('handled', Boolean),
    Column('meta_id', Integer, ForeignKey('meta.id')),
    Column('foreignid_id', Integer, ForeignKey('foreignid.id')),
)

stats = Table('stats', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    Column('date', Date),
    Column('value', Integer),
)

stats_lookups = Table('stats_lookups', metadata,
    Column('id', Integer, primary_key=True),
    Column('date', Date),
    Column('hour', Integer),
    Column('application_id', Integer, ForeignKey('application.id')),
    Column('count_nohits', Integer),
    Column('count_hits', Integer),
)

stats_user_agents = Table('stats_user_agents', metadata,
    Column('id', Integer, primary_key=True),
    Column('date', Date),
    Column('application_id', Integer, ForeignKey('application.id')),
    Column('user_agent', String),
    Column('ip', String),
    Column('count', Integer),
)

stats_top_accounts = Table('stats_top_accounts', metadata,
    Column('id', Integer, primary_key=True),
    Column('account_id', Integer, ForeignKey('account.id')),
    Column('count', Integer),
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
    Column('name', String),
)

foreignid = Table('foreignid', metadata,
    Column('id', Integer, primary_key=True),
    Column('vendor_id', Integer, ForeignKey('foreignid_vendor.id')),
    Column('name', String),
)

fingerprint = Table('fingerprint', metadata,
    Column('id', Integer, primary_key=True),
    Column('fingerprint', ARRAY(Integer)),
    Column('length', Integer),
    Column('bitrate', Integer),
    Column('format_id', Integer, ForeignKey('format.id')),
    Column('track_id', Integer, ForeignKey('track.id')),
    Column('submission_count', Integer),
)

fingerprint_source = Table('fingerprint_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('fingerprint_id', Integer, ForeignKey('fingerprint.id')),
    Column('submission_id', Integer, ForeignKey('submission.id')),
    Column('source_id', Integer, ForeignKey('source.id')),
)

fingerprint_index_queue = Table('fingerprint_index_queue', metadata,
    Column('fingerprint_id', Integer),
)

track_mbid = Table('track_mbid', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_id', Integer, ForeignKey('track.id')),
    Column('mbid', UUID),
    Column('created', DateTime),
    Column('submission_count', Integer),
    Column('disabled', Boolean),
)

track_mbid_source = Table('track_mbid_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_mbid_id', Integer, ForeignKey('track_mbid.id')),
    Column('submission_id', Integer, ForeignKey('submission.id')),
    Column('source_id', Integer, ForeignKey('source.id')),
)

track_mbid_change = Table('track_mbid_change', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_mbid_id', Integer, ForeignKey('track_mbid.id')),
    Column('account_id', Integer, ForeignKey('account.id')),
    Column('disabled', Boolean),
    Column('note', Text),
    Column('created', DateTime),
)

track_mbid_flag = Table('track_mbid_flag', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_mbid_id', Integer, ForeignKey('track_mbid.id')),
    Column('account_id', Integer, ForeignKey('account.id')),
    Column('handled', Boolean),
)

track_puid = Table('track_puid', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_id', Integer, ForeignKey('track.id')),
    Column('puid', UUID),
    Column('created', DateTime),
    Column('submission_count', Integer),
)

track_puid_source = Table('track_puid_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_puid_id', Integer, ForeignKey('track_puid.id')),
    Column('submission_id', Integer, ForeignKey('submission.id')),
    Column('source_id', Integer, ForeignKey('source.id')),
)

track_meta = Table('track_meta', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_id', Integer, ForeignKey('track.id')),
    Column('meta_id', Integer, ForeignKey('meta.id')),
    Column('created', DateTime),
    Column('submission_count', Integer),
)

track_meta_source = Table('track_meta_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_meta_id', Integer, ForeignKey('track_meta.id')),
    Column('submission_id', Integer, ForeignKey('submission.id')),
    Column('source_id', Integer, ForeignKey('source.id')),
)

track_foreignid = Table('track_foreignid', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_id', Integer, ForeignKey('track.id')),
    Column('foreignid_id', Integer, ForeignKey('track.id')),
    Column('created', DateTime),
    Column('submission_count', Integer),
)

track_foreignid_source = Table('track_foreignid_source', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_foreignid_id', Integer, ForeignKey('track_foreignid.id')),
    Column('submission_id', Integer, ForeignKey('submission.id')),
    Column('source_id', Integer, ForeignKey('source.id')),
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
