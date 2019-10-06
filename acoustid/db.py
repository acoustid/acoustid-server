import typing

from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Connection
from acoustid.tables import metadata


Session = sessionmaker()

AppDB = typing.NewType('AppDB', Connection)
FingerprintDB = typing.NewType('FingerprintDB', Connection)
IngestDB = typing.NewType('IngestDB', Connection)
MusicBrainzDB = typing.NewType('MusicBrainzDB', Connection)


def get_bind_args(engines):
    binds = {}
    for table in metadata.sorted_tables:
        bind_key = table.info.get('bind_key', 'app')
        if bind_key != 'app':
            binds[table] = engines[bind_key]
    return {'bind': engines['app'], 'binds': binds}


def get_session_args(script):
    kwargs = {'twophase': script.config.databases.use_two_phase_commit}
    kwargs.update(get_bind_args(script.db_engines))
    return kwargs


class DatabaseContext(object):

    def __init__(self, script):
        self.engines = script.db_engines
        self.session = Session(**get_session_args(script))

    def connection(self, bind_key):
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

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
