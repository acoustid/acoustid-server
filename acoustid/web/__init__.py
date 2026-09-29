# Copyright (C) 2014 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from typing import Any, Callable, Dict, Optional

from redis import Redis
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
        self.script = None  # type: Optional[Script]
        self.session_factory = sessionmaker(class_=Session)
        self.session = scoped_session(self.session_factory)

    def configure(self, script, scopefunc):
        # type: (Script, Callable[[], Any]) -> None
        self.engines = script.db_engines
        self.script = script
        self.session_factory.configure(**get_session_args(script))
        self.session = scoped_session(self.session_factory, scopefunc)

    def connection(self, bind_key, read_only=False):
        # type: (str, bool) -> Connection
        if read_only:
            read_only_bind_key = bind_key + ":ro"
            if read_only_bind_key in self.engines:
                bind_key = read_only_bind_key
        return self.session.connection(bind_arguments={"bind": self.engines[bind_key]})

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

    def get_redis(self):
        # type: () -> Redis
        """The redis client this process is configured with.

        Deliberately goes through the script rather than building a client of
        its own. Note that under redis sentinel this is not one shared client:
        Script.get_redis calls master_for(), which resolves the current master
        on every call. That is what makes a failover survivable, so it is not
        something to cache away.
        """
        assert self.script is not None, "db.configure() has not been called"
        return self.script.get_redis()


db = Database()
