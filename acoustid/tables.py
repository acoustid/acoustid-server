from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Boolean, Date, Text
from sqlalchemy.dialects.postgresql import ARRAY


metadata = MetaData()

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
    Column('gid', String),
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
    Column('mbid', String),
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
    Column('puid', String),
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

mb_artist = Table('s_artist', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    Column('gid', String),
    schema='musicbrainz',
)

mb_country = Table('country', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    Column('iso_code', String),
    schema='musicbrainz',
)

mb_release_group_primary_type = Table('release_group_primary_type', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    schema='musicbrainz',
)

mb_artist_credit = Table('s_artist_credit', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    Column('artist_count', Integer),
    schema='musicbrainz',
)

mb_artist_credit_name = Table('s_artist_credit_name', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    Column('artist_credit', Integer, ForeignKey('musicbrainz.s_artist_credit.id')),
    Column('artist', Integer, ForeignKey('musicbrainz.s_artist.id')),
    schema='musicbrainz',
)

mb_recording = Table('s_recording', metadata,
    Column('id', Integer, primary_key=True),
    Column('artist_credit', Integer, ForeignKey('musicbrainz.s_artist_credit.id')),
    Column('name', String),
    Column('gid', String),
    Column('comment', String),
    Column('length', Integer),
    schema='musicbrainz',
)

mb_recording_gid_redirect = Table('recording_gid_redirect', metadata,
    Column('gid', String, primary_key=True),
    Column('new_id', Integer, ForeignKey('musicbrainz.s_recording.id')),
    schema='musicbrainz',
)

mb_track = Table('s_track', metadata,
    Column('id', Integer, primary_key=True),
    Column('position', Integer),
    Column('tracklist', Integer, ForeignKey('musicbrainz.tracklist.id')),
    Column('recording', Integer, ForeignKey('musicbrainz.s_recording.id')),
    Column('artist_credit', Integer, ForeignKey('musicbrainz.s_artist_credit.id')),
    Column('name', String),
    Column('length', Integer),
    schema='musicbrainz',
)

mb_release = Table('s_release', metadata,
    Column('id', Integer, primary_key=True),
    Column('artist_credit', Integer, ForeignKey('musicbrainz.s_artist_credit.id')),
    Column('name', String),
    Column('gid', String),
    Column('date_year', Integer),
    Column('date_month', Integer),
    Column('date_day', Integer),
    Column('country', Integer, ForeignKey('musicbrainz.country.id')),
    Column('release_group', Integer, ForeignKey('musicbrainz.s_release_group.id')),
    schema='musicbrainz',
)

mb_release_group = Table('s_release_group', metadata,
    Column('id', Integer, primary_key=True),
    Column('artist_credit', Integer, ForeignKey('musicbrainz.s_artist_credit.id')),
    Column('name', String),
    Column('gid', String),
    Column('type', Integer, ForeignKey('musicbrainz.release_group_primary_type.id')),
    schema='musicbrainz',
)

mb_medium_format = Table('medium_format', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    schema='musicbrainz',
)

mb_medium = Table('medium', metadata,
    Column('id', Integer, primary_key=True),
    Column('release', Integer, ForeignKey('musicbrainz.s_release.id')),
    Column('tracklist', Integer, ForeignKey('musicbrainz.tracklist.id')),
    Column('position', Integer),
    Column('format', Integer, ForeignKey('musicbrainz.medium_format.id')),
    schema='musicbrainz',
)

mb_puid = Table('puid', metadata,
    Column('id', Integer, primary_key=True),
    Column('puid', String),
    schema='musicbrainz',
)

mb_recording_puid = Table('recording_puid', metadata,
    Column('id', Integer, primary_key=True),
    Column('puid', Integer, ForeignKey('musicbrainz.puid.id')),
    Column('recording', Integer, ForeignKey('musicbrainz.s_recording.id')),
    schema='musicbrainz',
)

mb_tracklist = Table('tracklist', metadata,
    Column('id', Integer, primary_key=True),
    Column('track_count', Integer),
    schema='musicbrainz',
)

