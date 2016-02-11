from sqlalchemy.orm import mapper, relationship
from sqlalchemy.ext.declarative import declarative_base
from acoustid import tables

Base = declarative_base(metadata=tables.metadata)


class Account(Base):
    __table__ = tables.account


class AccountOpenID(Base):
    __table__ = tables.account_openid

    account = relationship('Account')


class AccountGoogle(Base):
    __table__ = tables.account_google

    account = relationship('Account')


class Application(Base):
    __table__ = tables.application

    account = relationship('Account', foreign_keys=[tables.application.c.account_id])


class TrackMBID(Base):
    __table__ = tables.track_mbid

    track = relationship('Track')


class TrackMBIDChange(Base):
    __table__ = tables.track_mbid_change

    track_mbid = relationship('TrackMBID')
    account = relationship('Account')


class TrackMBIDSource(Base):
    __table__ = tables.track_mbid_source

    track_mbid = relationship('TrackMBID')
    source = relationship('Source')


class Source(Base):
    __table__ = tables.source

    application = relationship('Application')
    account = relationship('Account')


class Track(Base):
    __table__ = tables.track


class TrackMeta(Base):
    __table__ = tables.track_meta

    track = relationship('Track')
    meta = relationship('Meta')


class Meta(Base):
    __table__ = tables.meta


class StatsLookups(Base):
    __table__ = tables.stats_lookups

    application = relationship('Application')
