import zlib
from typing import TYPE_CHECKING, Any, Dict, NewType, Optional

from sqlalchemy import sql
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from acoustid.tables import metadata

if TYPE_CHECKING:
    from acoustid.script import Script

AppDB = NewType("AppDB", Connection)
FingerprintDB = NewType("FingerprintDB", Connection)
IngestDB = NewType("IngestDB", Connection)
MusicBrainzDB = NewType("MusicBrainzDB", Connection)


def pg_try_advisory_xact_lock(db: Connection, name: str, params: str | int) -> bool:
    lock_id1 = zlib.crc32(name.encode()) & 0x7FFFFFFF
    if isinstance(params, int):
        lock_id2 = params
    else:
        lock_id2 = zlib.crc32(params.encode()) & 0x7FFFFFFF
    return db.execute(
        sql.text("SELECT pg_try_advisory_xact_lock(:lock_id1, :lock_id2)"),
        {"lock_id1": lock_id1, "lock_id2": lock_id2},
    ).scalar_one()


def pg_advisory_xact_lock(db: Connection, name: str, params: str) -> None:
    lock_id1 = zlib.crc32(name.encode()) & 0x7FFFFFFF
    lock_id2 = zlib.crc32(params.encode()) & 0x7FFFFFFF
    db.execute(
        sql.text("SELECT pg_advisory_xact_lock(:lock_id1, :lock_id2)"),
        {"lock_id1": lock_id1, "lock_id2": lock_id2},
    )


def get_bind_args(engines):
    # type: (Dict[str, Engine]) -> Dict[str, Any]
    binds = {}
    default_bind_key = "app"
    for table in metadata.sorted_tables:
        bind_key = (
            table.info.get("bind_key", default_bind_key)
            if table.info
            else default_bind_key
        )
        if bind_key != default_bind_key:
            binds[table] = engines[bind_key]
    return {"bind": engines[default_bind_key], "binds": binds}


def get_session_args(script, use_two_phase_commit=None):
    # type: (Script, Optional[bool]) -> Dict[str, Any]
    kwargs = {}

    if script.config.databases.use_two_phase_commit:
        kwargs["twophase"] = script.config.databases.use_two_phase_commit
    if use_two_phase_commit:
        kwargs["twophase"] = use_two_phase_commit

    if script.config.databases.use_auto_commit:
        kwargs["autocommit"] = script.config.databases.use_auto_commit

    kwargs.update(get_bind_args(script.db_engines))
    return kwargs


class DatabaseContext(object):
    def __init__(self, script, use_two_phase_commit=None):
        # type: (Script, Optional[bool]) -> None
        self.engines = script.db_engines
        self.session = Session(
            **get_session_args(script, use_two_phase_commit=use_two_phase_commit)
        )

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

    def close(self):
        # type: () -> None
        self.session.close()

    def __enter__(self):
        # type: () -> DatabaseContext
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # type: (Any, Any, Any) -> None
        self.close()
