from typing import Any
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from acoustid import tables

Base = declarative_base(metadata=tables.metadata)  # type: Any


class Account(Base):
    __table__ = tables.account


class AccountOpenID(Base):
    __table__ = tables.account_openid

    account = relationship('Account')  # type: ignore


class AccountGoogle(Base):
    __table__ = tables.account_google

    account = relationship('Account')  # type: ignore


class Application(Base):
    __table__ = tables.application

    account = relationship('Account', foreign_keys=[tables.application.c.account_id])  # type: ignore


class TrackMBID(Base):
    __table__ = tables.track_mbid

    track = relationship('Track')  # type: ignore


class TrackMBIDChange(Base):
    __table__ = tables.track_mbid_change


class TrackMBIDSource(Base):
    __table__ = tables.track_mbid_source


class Source(Base):
    __table__ = tables.source

    application = relationship('Application')  # type: ignore
    account = relationship('Account')  # type: ignore


class Submission(Base):
    __table__ = tables.submission


class SubmissionResult(Base):
    __table__ = tables.submission_result


class Track(Base):
    __table__ = tables.track


class TrackMeta(Base):
    __table__ = tables.track_meta

    track = relationship('Track')  # type: ignore
    meta = relationship('Meta')  # type: ignore


class Fingerprint(Base):
    __table__ = tables.fingerprint
    track = relationship('Track')  # type: ignore


class Meta(Base):
    __table__ = tables.meta


class StatsLookups(Base):
    __table__ = tables.stats_lookups

    application = relationship('Application')  # type: ignore
