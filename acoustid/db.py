from typing import Dict, Any, NewType, TYPE_CHECKING

from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine, Connection
from acoustid.tables import metadata

if TYPE_CHECKING:
    from acoustid.script import Script

AppDB = NewType('AppDB', Connection)
FingerprintDB = NewType('FingerprintDB', Connection)
IngestDB = NewType('IngestDB', Connection)
MusicBrainzDB = NewType('MusicBrainzDB', Connection)


def get_bind_args(engines):
    # type: (Dict[str, Engine]) -> Dict[str, Any]
    binds = {}
    default_bind_key = 'app'
    for table in metadata.sorted_tables:
        bind_key = table.info.get('bind_key', default_bind_key) if table.info else default_bind_key
        if bind_key != default_bind_key:
            binds[table] = engines[bind_key]
    return {'bind': engines[default_bind_key], 'binds': binds}


def get_session_args(script):
    # type: (Script) -> Dict[str, Any]
    kwargs = {'twophase': script.config.databases.use_two_phase_commit}
    kwargs.update(get_bind_args(script.db_engines))
    return kwargs


class DatabaseContext(object):

    def __init__(self, script):
        # type: (Script) -> None
        self.engines = script.db_engines
        self.session = Session(**get_session_args(script))

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

    def close(self):
        # type: () -> None
        self.session.close()

    def __enter__(self):
        # type: () -> DatabaseContext
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # type: (Any, Any, Any) -> None
        self.close()
