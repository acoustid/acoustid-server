from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Boolean, Date
from sqlalchemy.dialects.postgresql import ARRAY


metadata = MetaData()

account = Table('account', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    Column('apikey', String),
    Column('mbuser', String),
    Column('created', DateTime),
    Column('lastlogin', DateTime),
    Column('submission_count', Integer),
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
)

track = Table('track', metadata,
    Column('id', Integer, primary_key=True),
    Column('created', DateTime),
)

format = Table('format', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
)

source = Table('source', metadata,
    Column('id', Integer, primary_key=True),
    Column('account_id', Integer, ForeignKey('account.id')),
    Column('application_id', Integer, ForeignKey('application.id')),
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

fingerprint = Table('fingerprint', metadata,
    Column('id', Integer, primary_key=True),
    Column('fingerprint', ARRAY(Integer)),
    Column('length', Integer),
    Column('bitrate', Integer),
    Column('source_id', Integer, ForeignKey('source.id')),
    Column('format_id', Integer, ForeignKey('format.id')),
    Column('track_id', Integer, ForeignKey('track.id')),
    Column('submission_id', Integer, ForeignKey('submission.id')),
    Column('meta_id', Integer, ForeignKey('meta.id')),
)

track_mbid = Table('track_mbid', metadata,
    Column('track_id', Integer, ForeignKey('track.id'), primary_key=True),
    Column('mbid', String, primary_key=True),
    Column('created', DateTime),
    Column('submission_id', Integer, ForeignKey('submission.id')),
)

mb_artist = Table('s_artist', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    Column('gid', String),
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
    Column('format', Integer, ForeignKey('musicbrainz.format.id')),
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

