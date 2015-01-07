from sqlalchemy.orm import mapper, relationship
from acoustid import tables

# TODO switch to declarative

class Application(object):
    pass


class User(object):
    pass


class TrackMBID(object):
    pass


class TrackMBIDChange(object):
    pass


class TrackMBIDSource(object):
    pass


class Source(object):
    pass


class Track(object):
    pass


class TrackMeta(object):
    pass


class Meta(object):
    pass


mapper(Application, tables.application)
mapper(User, tables.account)
mapper(Meta, tables.meta)
mapper(Track, tables.track)
mapper(TrackMeta, tables.track_meta, properties={
    'track': relationship(Track),
    'meta': relationship(Meta),
})
mapper(TrackMBID, tables.track_mbid, properties={
    'track': relationship(Track),
})
mapper(TrackMBIDChange, tables.track_mbid_change, properties={
    'user': relationship(User),
    'track_mbid': relationship(TrackMBID),
})
mapper(TrackMBIDSource, tables.track_mbid_source, properties={
    'source': relationship(Source),
    'track_mbid': relationship(TrackMBID),
})
mapper(Source, tables.source, properties={
    'application': relationship(Application),
})
