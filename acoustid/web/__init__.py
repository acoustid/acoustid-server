# Copyright (C) 2014 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from typing import Dict, Callable, Any
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.orm import scoped_session, sessionmaker
from acoustid.script import Script
from acoustid.db import (
    AppDB,
    FingerprintDB,
    IngestDB,
    MusicBrainzDB,
    Session,
    get_session_args,
)


class Database(object):

    def __init__(self):
        self.engines = {}  # type: Dict[str, Engine]
        self.session_factory = sessionmaker()
        self.session = scoped_session(Session)

    def configure(self, script, scopefunc):
        # type: (Script, Callable[[], Any]) -> None
        self.engines = script.db_engines
        self.session_factory.configure(**get_session_args(script))
        self.session = scoped_session(self.session_factory, scopefunc)

    def connection(self, bind_key):
        # type: (str) -> Connection
        return self.session.connection(bind=self.engines[bind_key])

    def get_app_db(self):
        # type: () -> AppDB
        return AppDB(self.connection('app'))

    def get_fingerprint_db(self):
        # type: () -> FingerprintDB
        return FingerprintDB(self.connection('fingerprint'))

    def get_ingest_db(self):
        # type: () -> IngestDB
        return IngestDB(self.connection('ingest'))

    def get_musicbrainz_db(self):
        # type: () -> MusicBrainzDB
        return MusicBrainzDB(self.connection('musicbrainz'))


db = Database()
