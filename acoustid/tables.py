from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime, Boolean
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
)

fingerprint = Table('fingerprint', metadata,
    Column('id', Integer, primary_key=True),
    Column('fingerprint', ARRAY(Integer)),
    Column('length', Integer),
    Column('bitrate', Integer),
    Column('source_id', Integer, ForeignKey('source.id')),
    Column('format_id', Integer, ForeignKey('format.id')),
    Column('track_id', Integer, ForeignKey('track.id')),
)

track_mbid = Table('track_mbid', metadata,
    Column('track_id', Integer, ForeignKey('track.id'), primary_key=True),
    Column('mbid', String, primary_key=True),
    Column('created', DateTime),
)

mb_artist = Table('artist', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String),
    Column('gid', String),
    schema='musicbrainz',
)

mb_track = Table('track', metadata,
    Column('id', Integer, primary_key=True),
    Column('artist', Integer, ForeignKey('musicbrainz.artist.id')),
    Column('name', String),
    Column('gid', String),
    Column('length', Integer),
    schema='musicbrainz',
)

mb_album = Table('album', metadata,
    Column('id', Integer, primary_key=True),
    Column('artist', Integer, ForeignKey('musicbrainz.artist.id')),
    Column('name', String),
    Column('gid', String),
    schema='musicbrainz',
)

mb_album_meta = Table('albummeta', metadata,
    Column('id', Integer, ForeignKey('musicbrainz.album.id'), primary_key=True),
    Column('tracks', String),
    schema='musicbrainz',
)

mb_album_track = Table('albumjoin', metadata,
    Column('id', Integer, primary_key=True),
    Column('album', Integer, ForeignKey('musicbrainz.album.id')),
    Column('track', Integer, ForeignKey('musicbrainz.track.id')),
    Column('sequence', Integer),
    schema='musicbrainz',
)

mb_puid = Table('puid', metadata,
    Column('id', Integer, primary_key=True),
    Column('puid', String),
    schema='musicbrainz',
)

mb_puid_track = Table('puidjoin', metadata,
    Column('id', Integer, primary_key=True),
    Column('puid', Integer, ForeignKey('musicbrainz.puid.id')),
    Column('track', Integer, ForeignKey('musicbrainz.track.id')),
    schema='musicbrainz',
)

