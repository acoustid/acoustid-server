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
``fingerprint``. The same goes for the index.html and index.json that every
directory carries: they are the archive's only directory listing, and they are
reproduced byte for byte.
"""

import datetime
import gzip
import json
import logging
import os
import random
from html import escape
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Protocol,
    Set,
    Union,
)

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


# The queries below come from pkg/export/queries.go, with the Go template
# placeholders replaced by psycopg2 ones. Note that two different delta
# predicates are in use: fingerprint and meta have no meaningful `updated`
# column to filter on, the rest do. That difference is deliberate.
#
# The link files -- track_fingerprint, track_mbid, track_puid, track_meta --
# publish no surrogate id. Nothing in the published data refers to one, and for
# the three real tables it is not even stable: merging two tracks keeps one row
# per distinct mbid/puid/meta_id and deletes the rest, so the row that survives
# for a given pair can have a different id than the one a consumer already
# holds. Publishing it invited people to key on it, which is what makes a merge
# look like two rows for one pair (issue #108). The column pairs are unique and
# are the real identity. `track.id`, `fingerprint.id` and `meta.id` are
# referenced from the other files as track_id, fingerprint_id and meta_id, and
# they stay.

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

# Yes, from fingerprint. The file is shaped like a track_fingerprint link table
# that does not exist yet -- the columns are the link, not the fingerprint, and
# the payload is deliberately absent. It used to publish the fingerprint id
# twice, once as `id` and once as `fingerprint_id`; only the second name means
# anything, and a link table would have had a surrogate id of its own that
# nothing would refer to. `fingerprint_id` is unique on its own here, because a
# fingerprint belongs to exactly one track.
EXPORT_TRACK_FINGERPRINT_UPDATE_QUERY = """
SELECT track_id, id AS fingerprint_id, submission_count, created, updated
FROM fingerprint
WHERE
  (created >= %(start)s AND created < %(end)s)
  OR
  (updated >= %(start)s AND updated < %(end)s)
"""

EXPORT_TRACK_MBID_UPDATE_QUERY = """
SELECT track_id, mbid, submission_count, nullif(disabled, false) AS disabled, created, updated
FROM track_mbid
WHERE
  (created >= %(start)s AND created < %(end)s)
  OR
  (updated >= %(start)s AND updated < %(end)s)
"""

EXPORT_TRACK_PUID_UPDATE_QUERY = """
SELECT track_id, puid, submission_count, created, updated
FROM track_puid
WHERE
  (created >= %(start)s AND created < %(end)s)
  OR
  (updated >= %(start)s AND updated < %(end)s)
"""

EXPORT_TRACK_META_UPDATE_QUERY = """
SELECT track_id, meta_id, submission_count, created, updated
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
    """Yield ``(start, end)`` day windows in UTC, most recent first.

    The first window ends at midnight today, so the day in progress is never
    exported and a file only appears once its day is over and final.

    The days are UTC days because that is what the published files are: every
    row in 2026-07-27-meta-update falls between 00:00:20Z and 23:59:49Z. That
    held only because the job happened to run with TZ unset, and a host on
    another zone would have written differently bounded data under the same
    file names -- which the existence check would then keep forever.
    """
    now = now.astimezone(datetime.timezone.utc)
    end_date = now.date()
    for _ in range(max_days):
        start_date = end_date - datetime.timedelta(days=1)
        yield (
            datetime.datetime.combine(
                start_date, datetime.time.min, tzinfo=datetime.timezone.utc
            ),
            datetime.datetime.combine(
                end_date, datetime.time.min, tzinfo=datetime.timezone.utc
            ),
        )
        end_date = start_date


def temp_path_for(path: str) -> str:
    """A hidden sibling of ``path``, in the same directory so a rename is atomic."""
    directory, file_name = os.path.split(path)
    return os.path.join(
        directory, ".{}.{}.tmp".format(file_name, random.randrange(1 << 63))
    )


def remove_temp_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Failed to delete temporary file %s", path)


def read_file(path: str) -> Optional[bytes]:
    """The contents of ``path``, or None if it is not there."""
    try:
        with open(path, "rb") as fileobj:
            return fileobj.read()
    except FileNotFoundError:
        return None


def delete_temp_files(directory: str, file_name: str) -> None:
    """Remove temp files left behind by a run that was killed mid-write."""
    try:
        entries = os.listdir(directory)
    except FileNotFoundError:
        return
    for entry in entries:
        if entry.endswith(".tmp") and file_name in entry:
            remove_temp_file(os.path.join(directory, entry))


INDEX_HTML_NAME = "index.html"
INDEX_JSON_NAME = "index.json"

# index.html lists these two, in this order, after the directory's real
# contents. index.json does not list them at all. That asymmetry is in the
# published files and is not something to tidy up.
INDEX_FILE_NAMES = (INDEX_HTML_NAME, INDEX_JSON_NAME)

# 1024-based, with the unit names index.html uses. The biggest published file
# is a 2.0 GB day from the original 2011 import, so GB is the highest unit that
# has ever been needed; the rest are here so that a bigger file would still
# render as something rather than as thousands of GB.
SIZE_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_size(size: int) -> str:
    """Render a byte count the way the published index.html does.

    Always one decimal place, so a 23-byte file reads ``23.0 B``. Ties round to
    an even last digit, which is what Go's float formatting did and what
    Python's does: 2024-12-05-track_fingerprint-update.jsonl.gz is 130304
    bytes, exactly 127.25 KB, and is published as ``127.2 KB``.
    """
    value = float(size)
    for unit in SIZE_UNITS[:-1]:
        if value < 1024.0:
            return "{:.1f} {}".format(value, unit)
        value /= 1024.0
    return "{:.1f} {}".format(value, SIZE_UNITS[-1])


class IndexEntry(NamedTuple):
    """One line of a directory listing.

    ``name`` carries a trailing slash for a directory, which is how index.json
    tells a directory from a file, and ``size`` is None for one -- directories
    are listed without a size in both formats.
    """

    name: str
    size: Optional[int]


def read_index_entries(directory: str) -> List[IndexEntry]:
    """List a directory the way the index files present it, sorted by name.

    The sizes are read off the filesystem rather than carried over from
    whatever wrote the files, which is what lets the indexes be rebuilt over a
    tree this process did not create.
    """
    entries = []
    with os.scandir(directory) as scan:
        for entry in scan:
            if entry.name.endswith(".tmp"):
                # A temp file is a half-written one. The rename in
                # export_query is there so that nothing ever sees a partial
                # .jsonl.gz, and an index that pointed at one would hand it
                # over anyway.
                continue
            if entry.name in INDEX_FILE_NAMES:
                # Left to render_index_html to append by name, so that a
                # listing never depends on the size of a file that listing is
                # about to change.
                continue
            if entry.is_dir():
                entries.append(IndexEntry(entry.name + "/", None))
            else:
                entries.append(IndexEntry(entry.name, entry.stat().st_size))
    entries.sort(key=lambda listed: listed.name)
    return entries


def index_title_path(root: str, directory: str) -> str:
    """The path index.html shows, as an absolute path within the tree.

    ``/`` at the top, then ``/2026`` and ``/2026/2026-07``: a leading slash and
    no trailing one.
    """
    relative = os.path.relpath(directory, root)
    if relative == os.curdir:
        return "/"
    return "/" + relative.replace(os.sep, "/")


def render_index_json(entries: List[IndexEntry]) -> bytes:
    """The machine-readable listing: compact, and with no trailing newline."""
    rows: List[Dict[str, Union[str, int]]] = []
    for entry in entries:
        row: Dict[str, Union[str, int]] = {"name": entry.name}
        if entry.size is not None:
            row["size"] = entry.size
        rows.append(row)
    return json.dumps(rows, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def render_index_html(title_path: str, entries: List[IndexEntry]) -> bytes:
    """The human-readable listing, byte for byte as it was published."""
    lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head><title>Index of {}</title></head>".format(escape(title_path)),
        "<body>",
        "<h1>Index of {}</h1>".format(escape(title_path)),
        "<ul>",
    ]
    for entry in entries:
        size = "" if entry.size is None else " ({})".format(format_size(entry.size))
        lines.append(
            '<li><a href="{0}">{0}</a>{1}</li>'.format(escape(entry.name), size)
        )
    lines.extend(["</ul>", "</body>", "</html>"])
    return "\n".join(lines).encode("utf-8")


class IndexWriter(object):
    """Writes the index.html and index.json that make the tree navigable.

    Every directory of the published archive carries both, and they are the
    only listing mechanism there is: the tree may well be served from a bucket,
    which has no directory listing of its own, so without these files the
    archive can only be read by someone who already knows every file name.
    They are a public interface like the data files, down to the bytes.

    Unlike a data file, an index that is already there is rewritten rather than
    left alone -- its directory's contents are the one thing that can have
    changed since it was written. It is only replaced when the bytes differ,
    though, so a pass over an unchanged tree leaves every mtime alone and a
    sync of the tree has nothing to re-upload.
    """

    def __init__(self, root: str) -> None:
        self.root = root

    def write_tree(self) -> int:
        """Rebuild every index under the root, reading only the filesystem.

        This is how a tree that was exported before the indexes existed gets
        them, without re-exporting a single data file.
        """
        count = 0
        for directory, dir_names, _ in os.walk(self.root):
            # Only so that the log of a first run over a large archive reads in
            # the order someone would look for.
            dir_names.sort()
            self.write(directory)
            count += 1
        return count

    def write(self, directory: str) -> None:
        try:
            entries = read_index_entries(directory)
        except FileNotFoundError:
            # A directory the run passed over without ever writing into.
            return
        self._write_index(
            os.path.join(directory, INDEX_JSON_NAME), render_index_json(entries)
        )
        self._write_index(
            os.path.join(directory, INDEX_HTML_NAME),
            render_index_html(
                index_title_path(self.root, directory),
                entries + [IndexEntry(name, None) for name in INDEX_FILE_NAMES],
            ),
        )

    def _write_index(self, path: str, data: bytes) -> None:
        directory, file_name = os.path.split(path)
        delete_temp_files(directory, file_name)
        if read_file(path) == data:
            logger.debug("Index %s is up to date", path)
            return
        logger.info("Writing %s", path)
        temp_path = temp_path_for(path)
        try:
            with open(temp_path, "wb") as fileobj:
                fileobj.write(data)
                fileobj.flush()
                os.fsync(fileobj.fileno())
            os.rename(temp_path, path)
        except BaseException:
            remove_temp_file(temp_path)
            raise


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
        self.index_writer = IndexWriter(directory)
        self.visited_directories: Set[str] = set()

    def run(self, now: Optional[datetime.datetime] = None) -> None:
        if now is None:
            now = datetime.datetime.now(datetime.timezone.utc)

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

        self.write_indexes()

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

        # Recorded whether or not anything gets written here, so that a run
        # also repairs an index that is missing or out of date -- which is the
        # state every directory of an already-exported tree starts in.
        self.visited_directories.add(directory)

        # Skipping files that are already there is what makes an hourly
        # schedule and backfilling the same operation: a run only fills holes.
        if os.path.exists(path):
            logger.debug("File %s already exists", path)
        else:
            logger.info("Exporting %s", path)
            os.makedirs(directory, exist_ok=True)
            self.export_query(path, table.query, start, end)

        delete_temp_files(directory, file_name)

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
            remove_temp_file(temp_path)
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

    def write_indexes(self) -> None:
        """Regenerate the listings for every directory this run went through.

        Collected during the run and written once at the end rather than after
        each file: a month directory is written into seven times a day, so a
        backfill of a few years would otherwise rewrite the same index
        thousands of times over.

        Every directory up to the root is included, because a new month changes
        its year's listing and a new year changes the top one. Those two are
        almost always unchanged, and an unchanged index is not rewritten.
        """
        directories = {self.directory}
        for directory in self.visited_directories:
            parts = [
                part
                for part in os.path.relpath(directory, self.directory).split(os.sep)
                if part != os.curdir
            ]
            for depth in range(1, len(parts) + 1):
                directories.add(os.path.join(self.directory, *parts[:depth]))
        for directory in sorted(directories):
            self.index_writer.write(directory)


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


def run_generate_indexes(directory: str) -> None:
    """Rebuild every index in an exported tree. No database involved.

    The export keeps the indexes of the directories it touches up to date, so
    this is for a tree that was exported before the indexes existed, or one
    that files have been moved into by hand.
    """
    count = IndexWriter(directory).write_tree()
    logger.info("Wrote the indexes of %d directories under %s", count, directory)
