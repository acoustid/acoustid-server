# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Daily incremental exports of the public data files.

This produces the files published at https://data.acoustid.org/, which stopped
being updated after 2026-07-27 when the job that wrote them was lost with the
old Kubernetes cluster.

There have been two Go implementations. The older one (acoustid/acoustid,
pkg/export, archived 2023) is where the file layout, the naming and the
iteration semantics come from. The one that actually wrote the published files
from 2024-12-05 onwards is go-acoustid/pkg/publicdata, and that is what the
output format here matches -- see build_copy_statement for the difference,
which is not cosmetic.

The layout, the file names and the SQL are a public interface -- real consumers
download these files and parse them -- so they are kept exactly as published,
including the quirk that ``track_fingerprint-update`` selects from
``fingerprint``.
"""

import datetime
import gzip
import logging
import os
import random
from typing import Any, Iterator, List, NamedTuple, Optional, Protocol, Union

from sqlalchemy import sql
from sqlalchemy.engine import Connection, Engine

from acoustid.const import EXPORT_MAX_DAYS

logger = logging.getLogger(__name__)

# Go's gzip.DefaultCompression, which is what the published files were written
# with. Level 9 would cost a lot of CPU for very little on this data.
GZIP_COMPRESS_LEVEL = 6

BUFFER_SIZE = 16 * 1024

FILE_NAME_SUFFIX = ".jsonl.gz"

# How long after a day ends before it is even considered for export. The
# horizon check below is what actually makes a day safe to export; this is
# there so that the first run after midnight is not routinely the one that
# finds a transaction still open, and so there is room for a read replica to
# catch up. Not configurable on purpose -- a value that has to be guessed per
# deployment is a value that will be guessed wrong.
SETTLE_DELAY = datetime.timedelta(hours=1)

# `created` and `updated` are current_timestamp, which is transaction START
# time, but a row only becomes visible when its transaction commits. So a day
# is only final once every transaction that began before the day ended has
# finished: until then one of them can still commit a row stamped inside that
# day, and the day file would be short by exactly those rows -- permanently,
# because a file that exists is never regenerated.
#
# Autovacuum is excluded because it runs long on tables this size and cannot
# introduce a row with a past `created`. Prepared transactions are included
# because two-phase commit is configurable here and they do not show up in
# pg_stat_activity. Other databases in the cluster are excluded because they
# cannot write these tables.
WRITE_HORIZON_QUERY = """
SELECT coalesce(
    least(
        (SELECT min(xact_start) FROM pg_stat_activity
          WHERE xact_start IS NOT NULL
            AND datname = current_database()
            AND pid <> pg_backend_pid()
            AND backend_type <> 'autovacuum worker'),
        (SELECT min(prepared) FROM pg_prepared_xacts
          WHERE database = current_database())
    ),
    clock_timestamp()
)
"""

# Without pg_read_all_stats, pg_stat_activity reports NULL xact_start for
# backends owned by other roles, so the horizon query would silently see only
# this session and every day would look settled. That failure looks exactly
# like success, which is why it is checked up front rather than left to be
# noticed in the output.
STATS_PRIVILEGE_QUERY = """
SELECT pg_has_role(current_user, 'pg_read_all_stats', 'USAGE')
"""


class ExportError(Exception):
    pass


# The queries below are copied verbatim from pkg/export/queries.go, with the Go
# template placeholders replaced by psycopg2 ones. Note that two different delta
# predicates are in use: fingerprint and meta have no meaningful `updated`
# column to filter on, the rest do. That difference is deliberate.

EXPORT_FINGERPRINT_UPDATE_QUERY = """
SELECT id, fingerprint, length, created
FROM fingerprint
WHERE created >= %(start)s AND created < %(end)s
"""

EXPORT_META_UPDATE_QUERY = """
SELECT id, track, artist, album, album_artist, track_no, disc_no, year, created
FROM meta
WHERE created >= %(start)s AND created < %(end)s
"""

EXPORT_TRACK_UPDATE_QUERY = """
SELECT id, gid, new_id, created, updated
FROM track
WHERE
  (created >= %(start)s AND created < %(end)s)
  OR
  (updated >= %(start)s AND updated < %(end)s)
"""

# Yes, from fingerprint. The file is named after the track_fingerprint table
# that this data used to live in; the column list is what consumers expect.
EXPORT_TRACK_FINGERPRINT_UPDATE_QUERY = """
SELECT id, track_id, id AS fingerprint_id, submission_count, created, updated
FROM fingerprint
WHERE
  (created >= %(start)s AND created < %(end)s)
  OR
  (updated >= %(start)s AND updated < %(end)s)
"""

EXPORT_TRACK_MBID_UPDATE_QUERY = """
SELECT id, track_id, mbid, submission_count, nullif(disabled, false) AS disabled, created, updated
FROM track_mbid
WHERE
  (created >= %(start)s AND created < %(end)s)
  OR
  (updated >= %(start)s AND updated < %(end)s)
"""

EXPORT_TRACK_PUID_UPDATE_QUERY = """
SELECT id, track_id, puid, submission_count, created, updated
FROM track_puid
WHERE
  (created >= %(start)s AND created < %(end)s)
  OR
  (updated >= %(start)s AND updated < %(end)s)
"""

EXPORT_TRACK_META_UPDATE_QUERY = """
SELECT id, track_id, meta_id, submission_count, created, updated
FROM track_meta
WHERE
  (created >= %(start)s AND created < %(end)s)
  OR
  (updated >= %(start)s AND updated < %(end)s)
"""


class ExportTable(NamedTuple):
    name: str
    query: str


TABLES = [
    ExportTable("fingerprint-update", EXPORT_FINGERPRINT_UPDATE_QUERY),
    ExportTable("meta-update", EXPORT_META_UPDATE_QUERY),
    ExportTable("track-update", EXPORT_TRACK_UPDATE_QUERY),
    ExportTable("track_fingerprint-update", EXPORT_TRACK_FINGERPRINT_UPDATE_QUERY),
    ExportTable("track_mbid-update", EXPORT_TRACK_MBID_UPDATE_QUERY),
    ExportTable("track_puid-update", EXPORT_TRACK_PUID_UPDATE_QUERY),
    ExportTable("track_meta-update", EXPORT_TRACK_META_UPDATE_QUERY),
]


def build_copy_statement(query: str) -> str:
    """Wrap a query so that COPY streams it out as JSON Lines.

    json_strip_nulls is what drops the null fields, and generating the JSON
    server-side is what lets us stream straight into gzip instead of building
    rows in Python.

    The CSV format, with a delimiter and a quote character that JSON can never
    contain, is what keeps the output raw. COPY's default text format escapes
    every backslash, so the JSON escaping in a title like Recitatif : "..."
    comes back with doubled backslashes and the line stops being valid JSON.
    The published files did look like that until 2024-12-04; from 2024-12-05
    on they are plain JSON, because go-acoustid/pkg/publicdata stopped using
    COPY and wrote the rows out itself. This gets those same bytes back
    without giving up the streaming COPY.

    row_to_json escapes every control character, so the two bytes used below
    cannot occur in the value and CSV never has a reason to quote anything.
    """
    return (
        "COPY (SELECT json_strip_nulls(row_to_json(r)) FROM ("
        + query
        + ") r) TO STDOUT WITH (FORMAT csv, DELIMITER E'\\x01', QUOTE E'\\b')"
    )


def file_name_for(day: datetime.date, name: str) -> str:
    return "{}-{}{}".format(day.strftime("%Y-%m-%d"), name, FILE_NAME_SUFFIX)


def relative_path_for(day: datetime.date, name: str) -> str:
    return os.path.join(
        day.strftime("%Y"), day.strftime("%Y-%m"), file_name_for(day, name)
    )


def iter_days(
    now: datetime.datetime, max_days: int
) -> Iterator[tuple[datetime.datetime, datetime.datetime]]:
    """Yield ``(start, end)`` day windows, most recent first.

    The first window ends at midnight today, so the day in progress is never
    exported and a file only appears once its day is over and final.
    """
    end_date = now.date()
    tz = now.tzinfo
    for _ in range(max_days):
        start_date = end_date - datetime.timedelta(days=1)
        yield (
            datetime.datetime.combine(start_date, datetime.time.min, tzinfo=tz),
            datetime.datetime.combine(end_date, datetime.time.min, tzinfo=tz),
        )
        end_date = start_date


class SupportsWrite(Protocol):
    """Anything the COPY output can be poured into, gzip.GzipFile in practice."""

    def write(self, data: bytes, /) -> object:
        """Write out one chunk."""


class _BytesWriter:
    """Feeds psycopg2's COPY output into a binary file object.

    psycopg2 hands us ``str`` when it decides the destination is a text file
    and ``bytes`` otherwise. Accepting both means the gzip stream gets bytes
    either way, without depending on how that decision is made.
    """

    def __init__(self, fileobj: SupportsWrite) -> None:
        self._fileobj = fileobj

    def write(self, data: Union[str, bytes]) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._fileobj.write(data)


class Exporter(object):
    def __init__(
        self,
        db: Connection,
        directory: str,
        max_days: int = EXPORT_MAX_DAYS,
        tables: Optional[List[ExportTable]] = None,
    ) -> None:
        self.db = db
        self.directory = directory
        self.max_days = max_days
        self.tables = TABLES if tables is None else tables

    def run(self, now: Optional[datetime.datetime] = None) -> None:
        if now is None:
            now = datetime.datetime.now().astimezone()

        # Taken once, before any exporting. The real horizon only moves
        # forward while the run works through the days, so a value read at the
        # start can only hold a day back that had in fact become safe -- never
        # release one that has not.
        horizon = min(self.get_write_horizon(), now - SETTLE_DELAY)

        held_back = []
        for start, end in iter_days(now, self.max_days):
            if end > horizon:
                held_back.append(start.date())
                continue
            for table in self.tables:
                self.export_delta_file(table, start, end)

        if held_back:
            # One day held back is the normal state shortly after midnight.
            # More than that means something is sitting on an open transaction,
            # and it needs to be noticed well before those days fall out of the
            # max_days window, because at that point they are lost for good.
            logger.info(
                "Holding back %d day(s) from %s onwards, nothing written for "
                "them: cutoff is %s",
                len(held_back),
                min(held_back),
                horizon,
            )

    def get_write_horizon(self) -> datetime.datetime:
        """The time before which no transaction is still able to write."""
        horizon = self.db.execute(sql.text(WRITE_HORIZON_QUERY)).scalar_one()
        assert isinstance(horizon, datetime.datetime)
        return horizon

    def export_delta_file(
        self, table: ExportTable, start: datetime.datetime, end: datetime.datetime
    ) -> None:
        day = start.date()
        directory = os.path.join(
            self.directory, day.strftime("%Y"), day.strftime("%Y-%m")
        )
        file_name = file_name_for(day, table.name)
        path = os.path.join(directory, file_name)

        # Skipping files that are already there is what makes an hourly
        # schedule and backfilling the same operation: a run only fills holes.
        if os.path.exists(path):
            logger.debug("File %s already exists", path)
        else:
            logger.info("Exporting %s", path)
            os.makedirs(directory, exist_ok=True)
            self.export_query(path, table.query, start, end)

        self.delete_temp_files(directory, file_name)

    def export_query(
        self,
        path: str,
        query: str,
        start: datetime.datetime,
        end: datetime.datetime,
    ) -> None:
        """Write one export file, publishing it with an atomic rename.

        Anything reading the directory -- a consumer, or the sync that copies
        it elsewhere -- must never see a half-written .jsonl.gz, so the data
        goes to a temp file in the same directory first.
        """
        directory, file_name = os.path.split(path)
        temp_path = os.path.join(
            directory, ".{}.{}.tmp".format(file_name, random.randrange(1 << 63))
        )
        try:
            with open(temp_path, "wb", BUFFER_SIZE) as fileobj:
                # filename="" keeps the temp file's name out of the gzip
                # header, mtime=0 keeps the output byte-identical between runs.
                with gzip.GzipFile(
                    filename="",
                    mode="wb",
                    compresslevel=GZIP_COMPRESS_LEVEL,
                    fileobj=fileobj,
                    mtime=0,
                ) as gzip_file:
                    self.copy_query_to_file(gzip_file, query, start, end)
                fileobj.flush()
                os.fsync(fileobj.fileno())
            os.rename(temp_path, path)
        except BaseException:
            self._remove_temp_file(temp_path)
            raise

    def copy_query_to_file(
        self,
        fileobj: SupportsWrite,
        query: str,
        start: datetime.datetime,
        end: datetime.datetime,
    ) -> None:
        raw_connection: Any = self.db.connection
        with raw_connection.cursor() as cursor:
            statement = cursor.mogrify(
                build_copy_statement(query), {"start": start, "end": end}
            )
            cursor.copy_expert(statement, _BytesWriter(fileobj), size=BUFFER_SIZE)

    def delete_temp_files(self, directory: str, file_name: str) -> None:
        """Remove temp files left behind by a run that was killed mid-write."""
        try:
            entries = os.listdir(directory)
        except FileNotFoundError:
            return
        for entry in entries:
            if entry.endswith(".tmp") and file_name in entry:
                self._remove_temp_file(os.path.join(directory, entry))

    def _remove_temp_file(self, path: str) -> None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError:
            logger.exception("Failed to delete temporary file %s", path)


def check_stats_privilege(db: Connection) -> None:
    if not db.execute(sql.text(STATS_PRIVILEGE_QUERY)).scalar_one():
        raise ExportError(
            "The export needs to see when the oldest running transaction "
            "started, and without pg_read_all_stats it would see only its own "
            "session and treat every day as settled. Run: GRANT "
            "pg_read_all_stats TO {}.".format(
                db.execute(sql.text("SELECT current_user")).scalar_one()
            )
        )


def run_export(
    engine: Engine,
    directory: str,
    max_days: int = EXPORT_MAX_DAYS,
    now: Optional[datetime.datetime] = None,
) -> None:
    # AUTOCOMMIT so that each COPY gets its own snapshot instead of one
    # transaction being held open for the whole run, which on a long backfill
    # would keep a read replica from applying WAL.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
        # COPY encodes its output in the client encoding, and the files are
        # published as UTF-8 whatever the client happens to default to.
        db.exec_driver_sql("SET client_encoding TO 'UTF8'")
        check_stats_privilege(db)
        Exporter(db, directory, max_days=max_days).run(now=now)
