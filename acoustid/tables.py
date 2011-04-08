from sqlalchemy import Table, Column, Integer, String, MetaData, ForeignKey, DateTime
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

