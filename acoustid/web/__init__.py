# Copyright (C) 2014 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from typing import Any, Callable, Dict

from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import scoped_session, sessionmaker

from acoustid.db import (
    AppDB,
    FingerprintDB,
    IngestDB,
    MusicBrainzDB,
    Session,
    get_session_args,
)
from acoustid.script import Script


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

    def connection(self, bind_key, read_only=False):
        # type: (str, bool) -> Connection
        if read_only:
            read_only_bind_key = bind_key + ":ro"
            if read_only_bind_key in self.engines:
                bind_key = read_only_bind_key
        return self.session.connection(bind=self.engines[bind_key])

    def get_app_db(self, read_only=False):
        # type: (bool) -> AppDB
        return AppDB(self.connection("app", read_only))

    def get_fingerprint_db(self, read_only=False):
        # type: (bool) -> FingerprintDB
        return FingerprintDB(self.connection("fingerprint", read_only))

    def get_ingest_db(self, read_only=False):
        # type: (bool) -> IngestDB
        return IngestDB(self.connection("ingest", read_only))

    def get_musicbrainz_db(self, read_only=True):
        # type: (bool) -> MusicBrainzDB
        return MusicBrainzDB(self.connection("musicbrainz", read_only))


db = Database()
