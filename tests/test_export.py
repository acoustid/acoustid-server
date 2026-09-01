# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
import gzip
import json
import os
import tempfile
from typing import Callable, List, Optional

import pytest
from sqlalchemy import sql

from acoustid import export as export_module
from acoustid.config import DatabaseConfig, DatabasesConfig
from acoustid.export import (
    SETTLE_DELAY,
    TABLES,
    Exporter,
    ExportError,
    ExportTable,
    SupportsWrite,
    build_copy_statement,
    check_stats_privilege,
    file_name_for,
    iter_days,
    relative_path_for,
    run_export,
)
from acoustid.script import Script

from . import with_script

UTC = datetime.timezone.utc

# The day the published files stop at, which makes the fixtures read the same
# way as the outage this was written for.
DAY = datetime.date(2026, 7, 27)
NOW = datetime.datetime(2026, 7, 28, 9, 30, tzinfo=UTC)


def read_only_bind_key(script: Script) -> str:
    return script.config.databases.read_only_bind_key("fingerprint")


def in_day(hour: int, day: datetime.date = DAY) -> datetime.datetime:
    return datetime.datetime(day.year, day.month, day.day, hour, tzinfo=UTC)


class FakeExporter(Exporter):
    """An exporter whose COPY writes canned bytes instead of talking to a database."""

    def __init__(self, directory: str, **kwargs) -> None:
        super().__init__(None, directory, **kwargs)  # type: ignore[arg-type]
        self.exported: List[str] = []
        self.payload = b'{"id":1}\n'
        self.fail_with: Optional[Exception] = None
        self.check_while_writing: Optional[Callable[[], None]] = None
        # Far enough ahead that only the settle delay applies, unless a
        # test moves it.
        self.horizon = datetime.datetime(2100, 1, 1, tzinfo=UTC)

    def get_write_horizon(self) -> datetime.datetime:
        return self.horizon

    def copy_query_to_file(self, fileobj, query, start, end):
        # type: (SupportsWrite, str, datetime.datetime, datetime.datetime) -> None
        self.exported.append(query)
        if self.check_while_writing is not None:
            self.check_while_writing()
        if self.fail_with is not None:
            raise self.fail_with
        fileobj.write(self.payload)


def one_table() -> List[ExportTable]:
    return [ExportTable("track-update", "SELECT 1")]


def test_iter_days_walks_backwards_from_midnight_today() -> None:
    days = list(iter_days(NOW, 3))
    assert days == [
        (in_day(0, datetime.date(2026, 7, 27)), in_day(0, datetime.date(2026, 7, 28))),
        (in_day(0, datetime.date(2026, 7, 26)), in_day(0, datetime.date(2026, 7, 27))),
        (in_day(0, datetime.date(2026, 7, 25)), in_day(0, datetime.date(2026, 7, 26))),
    ]


def test_iter_days_never_includes_the_day_in_progress() -> None:
    """A file must only appear once its day is over and can no longer change."""
    starts = [start.date() for start, _ in iter_days(NOW, 30)]
    assert NOW.date() not in starts
    assert starts[0] == NOW.date() - datetime.timedelta(days=1)


def test_iter_days_windows_are_half_open_and_contiguous() -> None:
    days = list(iter_days(NOW, 5))
    for (start, end), (earlier_start, earlier_end) in zip(days, days[1:]):
        assert earlier_end == start
        assert end - start == datetime.timedelta(days=1)
        _ = earlier_start


def test_path_layout_matches_the_published_one() -> None:
    assert file_name_for(DAY, "track_mbid-update") == (
        "2026-07-27-track_mbid-update.jsonl.gz"
    )
    assert relative_path_for(DAY, "track_mbid-update") == os.path.join(
        "2026", "2026-07", "2026-07-27-track_mbid-update.jsonl.gz"
    )


def test_exports_every_table_into_the_day_directory() -> None:
    with tempfile.TemporaryDirectory() as directory:
        exporter = FakeExporter(directory, max_days=1)
        exporter.run(now=NOW)
        written = sorted(os.listdir(os.path.join(directory, "2026", "2026-07")))
        assert written == sorted(file_name_for(DAY, table.name) for table in TABLES)


def test_skips_files_that_are_already_there() -> None:
    """Re-running must not regenerate anything -- that is what lets this run hourly."""
    with tempfile.TemporaryDirectory() as directory:
        first = FakeExporter(directory, max_days=1, tables=one_table())
        first.run(now=NOW)
        path = os.path.join(directory, relative_path_for(DAY, "track-update"))
        before = os.stat(path)

        second = FakeExporter(directory, max_days=1, tables=one_table())
        second.run(now=NOW)

        assert second.exported == []
        assert os.stat(path).st_mtime_ns == before.st_mtime_ns


def test_backfills_only_the_missing_days() -> None:
    with tempfile.TemporaryDirectory() as directory:
        FakeExporter(directory, max_days=1, tables=one_table()).run(now=NOW)

        exporter = FakeExporter(directory, max_days=4, tables=one_table())
        exporter.run(now=NOW)

        assert len(exporter.exported) == 3
        days = sorted(os.listdir(os.path.join(directory, "2026", "2026-07")))
        assert days == [
            "2026-07-24-track-update.jsonl.gz",
            "2026-07-25-track-update.jsonl.gz",
            "2026-07-26-track-update.jsonl.gz",
            "2026-07-27-track-update.jsonl.gz",
        ]


def test_backfill_crosses_month_and_year_boundaries() -> None:
    with tempfile.TemporaryDirectory() as directory:
        exporter = FakeExporter(directory, max_days=3, tables=one_table())
        exporter.run(now=datetime.datetime(2026, 1, 2, 4, 0, tzinfo=UTC))
        assert os.path.exists(
            os.path.join(
                directory, "2026", "2026-01", "2026-01-01-track-update.jsonl.gz"
            )
        )
        assert os.path.exists(
            os.path.join(
                directory, "2025", "2025-12", "2025-12-31-track-update.jsonl.gz"
            )
        )
        assert os.path.exists(
            os.path.join(
                directory, "2025", "2025-12", "2025-12-30-track-update.jsonl.gz"
            )
        )


def test_target_file_only_appears_once_it_is_complete() -> None:
    """A consumer, or the sync to the bucket, must never see a partial file."""
    with tempfile.TemporaryDirectory() as directory:
        exporter = FakeExporter(directory, max_days=1, tables=one_table())
        path = os.path.join(directory, relative_path_for(DAY, "track-update"))
        target_seen: List[bool] = []
        entries_seen: List[List[str]] = []

        def check() -> None:
            target_seen.append(os.path.exists(path))
            entries_seen.append(os.listdir(os.path.dirname(path)))

        exporter.check_while_writing = check
        exporter.run(now=NOW)

        assert target_seen == [False]
        assert len(entries_seen[0]) == 1
        assert entries_seen[0][0].endswith(".tmp")
        assert entries_seen[0][0].startswith(".2026-07-27-track-update.jsonl.gz.")
        assert os.listdir(os.path.dirname(path)) == [os.path.basename(path)]


def test_failed_export_leaves_nothing_behind() -> None:
    with tempfile.TemporaryDirectory() as directory:
        exporter = FakeExporter(directory, max_days=1, tables=one_table())
        exporter.fail_with = RuntimeError("connection lost")

        with pytest.raises(RuntimeError):
            exporter.run(now=NOW)

        assert os.listdir(os.path.join(directory, "2026", "2026-07")) == []


def test_sweeps_temp_files_left_by_a_killed_run() -> None:
    with tempfile.TemporaryDirectory() as directory:
        day_directory = os.path.join(directory, "2026", "2026-07")
        os.makedirs(day_directory)
        stale = os.path.join(
            day_directory, ".2026-07-27-track-update.jsonl.gz.884425.tmp"
        )
        unrelated = os.path.join(day_directory, "2026-07-27-meta-update.jsonl.gz")
        with open(stale, "wb") as f:
            f.write(b"half a file")
        with open(unrelated, "wb") as f:
            f.write(b"")

        FakeExporter(directory, max_days=1, tables=one_table()).run(now=NOW)

        assert not os.path.exists(stale)
        assert os.path.exists(unrelated)


def test_sweeps_temp_files_even_when_the_file_already_exists() -> None:
    """The sweep is the only thing that cleans up, so skipping must not skip it."""
    with tempfile.TemporaryDirectory() as directory:
        FakeExporter(directory, max_days=1, tables=one_table()).run(now=NOW)
        day_directory = os.path.join(directory, "2026", "2026-07")
        stale = os.path.join(day_directory, ".2026-07-27-track-update.jsonl.gz.99.tmp")
        with open(stale, "wb") as f:
            f.write(b"leftover")

        FakeExporter(directory, max_days=1, tables=one_table()).run(now=NOW)

        assert not os.path.exists(stale)


def test_gzip_header_matches_the_published_files() -> None:
    """No embedded name, no timestamp -- the same header the Go writer produced."""
    with tempfile.TemporaryDirectory() as directory:
        FakeExporter(directory, max_days=1, tables=one_table()).run(now=NOW)
        path = os.path.join(directory, relative_path_for(DAY, "track-update"))
        with open(path, "rb") as f:
            header = f.read(10)
        assert header == b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff"
        with gzip.open(path, "rb") as gz:
            assert gz.read() == b'{"id":1}\n'


def test_copy_statement_does_not_use_the_escaping_text_format() -> None:
    statement = build_copy_statement("SELECT 1")
    assert statement.startswith(
        "COPY (SELECT json_strip_nulls(row_to_json(r)) FROM (SELECT 1) r) TO STDOUT"
    )
    assert "FORMAT csv" in statement


def read_export(directory: str, name: str) -> List[dict]:
    path = os.path.join(directory, relative_path_for(DAY, name))
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def insert_fixtures(script: Script) -> None:
    """Rows dated inside, before and after the day being exported."""
    before = in_day(12, DAY - datetime.timedelta(days=2))
    inside = in_day(12)
    after = in_day(12, DAY + datetime.timedelta(days=1))

    with script.context() as ctx:
        db = ctx.db.get_fingerprint_db()
        db.execute(
            sql.text(
                "INSERT INTO track (id, gid, created, updated) VALUES"
                " (101, '2b2ecb1e-9f1a-4c0a-8f56-9b6b6b1a0001', :inside, NULL),"
                " (102, '2b2ecb1e-9f1a-4c0a-8f56-9b6b6b1a0002', :before, :inside),"
                " (103, '2b2ecb1e-9f1a-4c0a-8f56-9b6b6b1a0003', :after, NULL)"
            ),
            {"before": before, "inside": inside, "after": after},
        )
        db.execute(
            sql.text(
                "INSERT INTO fingerprint"
                " (id, fingerprint, length, track_id, submission_count, created, updated)"
                " VALUES"
                " (201, '{1,2,3}', 120, 101, 1, :inside, NULL),"
                " (202, '{4,5,6}', 130, 102, 2, :before, :inside),"
                " (203, '{7,8,9}', 140, 103, 1, :after, NULL)"
            ),
            {"before": before, "inside": inside, "after": after},
        )
        db.execute(
            sql.text(
                "INSERT INTO meta (id, track, artist, album, created) VALUES"
                " (301, :quoted, NULL, NULL, :inside),"
                " (302, 'Later', NULL, NULL, :after)"
            ),
            {
                "inside": inside,
                "after": after,
                # A quote and a backslash, which is what the COPY text format
                # would have mangled into invalid JSON.
                "quoted": 'Récitatif : "Je Ne Puis" \\ 武國忠',
            },
        )
        db.execute(
            sql.text(
                "INSERT INTO track_mbid"
                " (id, track_id, mbid, submission_count, disabled, created, updated)"
                " VALUES"
                " (401, 101, 'b81f83ee-4da4-11e0-9ed8-002522535601', 1, false, :inside, NULL),"
                " (402, 102, 'b81f83ee-4da4-11e0-9ed8-002522535602', 3, true, :before, :inside)"
            ),
            {"before": before, "inside": inside},
        )
        db.execute(
            sql.text(
                "INSERT INTO track_puid"
                " (id, track_id, puid, submission_count, created, updated) VALUES"
                " (501, 101, 'c81f83ee-4da4-11e0-9ed8-002522535601', 1, :inside, NULL)"
            ),
            {"inside": inside},
        )
        db.execute(
            sql.text(
                "INSERT INTO track_meta"
                " (id, track_id, meta_id, submission_count, created, updated) VALUES"
                " (601, 101, 301, 1, :inside, NULL)"
            ),
            {"inside": inside},
        )
        ctx.db.session.commit()


@with_script
def test_exports_all_seven_files_for_a_complete_day(script: Script) -> None:
    insert_fixtures(script)
    with tempfile.TemporaryDirectory() as directory:
        run_export(script.db_engines["fingerprint:ro"], directory, max_days=1, now=NOW)

        written = sorted(os.listdir(os.path.join(directory, "2026", "2026-07")))
        assert written == sorted(file_name_for(DAY, t.name) for t in TABLES)

        assert sorted(row["id"] for row in read_export(directory, "track-update")) == [
            101,
            102,
        ]
        assert [
            (row["track_id"], row["puid"])
            for row in read_export(directory, "track_puid-update")
        ] == [(101, "c81f83ee-4da4-11e0-9ed8-002522535601")]
        assert [
            (row["track_id"], row["meta_id"])
            for row in read_export(directory, "track_meta-update")
        ] == [(101, 301)]


@with_script
def test_fingerprint_and_meta_filter_on_created_only(script: Script) -> None:
    """fingerprint 202 was updated inside the day but created before it.

    It belongs in track_fingerprint-update and not in fingerprint-update. The
    two files come from the same table and differ only in that predicate.
    """
    insert_fixtures(script)
    with tempfile.TemporaryDirectory() as directory:
        run_export(script.db_engines["fingerprint:ro"], directory, max_days=1, now=NOW)

        assert [row["id"] for row in read_export(directory, "fingerprint-update")] == [
            201
        ]
        assert sorted(
            row["id"] for row in read_export(directory, "track_fingerprint-update")
        ) == [201, 202]
        assert [row["id"] for row in read_export(directory, "meta-update")] == [301]


@with_script
def test_track_fingerprint_repeats_the_id_as_fingerprint_id(script: Script) -> None:
    insert_fixtures(script)
    with tempfile.TemporaryDirectory() as directory:
        run_export(script.db_engines["fingerprint:ro"], directory, max_days=1, now=NOW)
        rows = {
            row["id"]: row for row in read_export(directory, "track_fingerprint-update")
        }
        assert rows[201]["fingerprint_id"] == 201
        assert rows[201]["track_id"] == 101
        assert "fingerprint" not in rows[201]


@with_script
def test_null_fields_are_dropped(script: Script) -> None:
    insert_fixtures(script)
    with tempfile.TemporaryDirectory() as directory:
        run_export(script.db_engines["fingerprint:ro"], directory, max_days=1, now=NOW)

        rows = {row["id"]: row for row in read_export(directory, "track-update")}
        assert "updated" not in rows[101]
        assert "updated" in rows[102]
        assert "new_id" not in rows[101]

        meta = read_export(directory, "meta-update")[0]
        assert "artist" not in meta
        assert "album" not in meta


@with_script
def test_disabled_is_only_present_when_true(script: Script) -> None:
    """nullif(disabled, false) plus json_strip_nulls is how the flag disappears."""
    insert_fixtures(script)
    with tempfile.TemporaryDirectory() as directory:
        run_export(script.db_engines["fingerprint:ro"], directory, max_days=1, now=NOW)
        rows = {row["mbid"]: row for row in read_export(directory, "track_mbid-update")}
        assert "disabled" not in rows["b81f83ee-4da4-11e0-9ed8-002522535601"]
        assert rows["b81f83ee-4da4-11e0-9ed8-002522535602"]["disabled"] is True


@with_script
def test_quotes_and_backslashes_survive_as_valid_json(script: Script) -> None:
    """The regression that COPY's default text format would reintroduce."""
    insert_fixtures(script)
    with tempfile.TemporaryDirectory() as directory:
        run_export(script.db_engines["fingerprint:ro"], directory, max_days=1, now=NOW)
        path = os.path.join(directory, relative_path_for(DAY, "meta-update"))
        with gzip.open(path, "rb") as f:
            raw = f.read()

        assert b'\\\\"' not in raw
        assert json.loads(raw.decode("utf-8").splitlines()[0])["track"] == (
            'Récitatif : "Je Ne Puis" \\ 武國忠'
        )


@with_script
def test_empty_day_still_produces_a_file(script: Script) -> None:
    """A day with no rows gets an empty file, not a missing one -- otherwise
    every later run would try to export it again."""
    insert_fixtures(script)
    with tempfile.TemporaryDirectory() as directory:
        empty_day_now = datetime.datetime(2026, 7, 20, 9, 30, tzinfo=UTC)
        run_export(
            script.db_engines[read_only_bind_key(script)],
            directory,
            max_days=1,
            now=empty_day_now,
        )
        path = os.path.join(
            directory, "2026", "2026-07", "2026-07-19-track-update.jsonl.gz"
        )
        with gzip.open(path, "rb") as f:
            assert f.read() == b""


def test_read_only_bind_key_prefers_a_configured_replica() -> None:
    config = DatabasesConfig()
    config.databases["fingerprint:ro"].host = "replica.example"
    assert config.read_only_bind_key("fingerprint") == "fingerprint:ro"


def test_read_only_bind_key_falls_back_when_no_replica_is_configured() -> None:
    """Without this, an env-only deployment would connect to the default
    database name on localhost instead of the fingerprint database."""
    config = DatabasesConfig()
    config.databases["fingerprint"].host = "pg-fingerprint"
    config.databases["fingerprint"].name = "acoustid_fingerprint"
    assert config.databases["fingerprint:ro"] == DatabaseConfig()
    assert config.read_only_bind_key("fingerprint") == "fingerprint"


def day_directory(directory: str) -> str:
    return os.path.join(directory, "2026", "2026-07")


def test_day_is_held_back_while_an_older_transaction_is_open() -> None:
    """A transaction that started before the day ended can still commit a row
    stamped inside it, and the file would be short by exactly those rows."""
    with tempfile.TemporaryDirectory() as directory:
        exporter = FakeExporter(directory, max_days=1, tables=one_table())
        exporter.horizon = in_day(23, DAY)  # an hour before the day ended
        exporter.run(now=NOW)

        assert exporter.exported == []
        assert not os.path.exists(day_directory(directory))


def test_a_held_back_day_is_only_delayed_not_lost() -> None:
    with tempfile.TemporaryDirectory() as directory:
        first = FakeExporter(directory, max_days=1, tables=one_table())
        first.horizon = in_day(23, DAY)
        first.run(now=NOW)
        assert first.exported == []

        second = FakeExporter(directory, max_days=1, tables=one_table())
        second.run(now=NOW + datetime.timedelta(hours=1))

        assert len(second.exported) == 1
        assert os.path.exists(
            os.path.join(directory, relative_path_for(DAY, "track-update"))
        )


def test_only_the_days_the_horizon_has_not_reached_are_held_back() -> None:
    with tempfile.TemporaryDirectory() as directory:
        exporter = FakeExporter(directory, max_days=3, tables=one_table())
        # Settled through the end of 2026-07-26, still open inside 2026-07-27.
        exporter.horizon = in_day(4, DAY)
        exporter.run(now=NOW)

        assert sorted(os.listdir(day_directory(directory))) == [
            "2026-07-25-track-update.jsonl.gz",
            "2026-07-26-track-update.jsonl.gz",
        ]


def test_settle_delay_holds_back_a_day_that_has_only_just_ended() -> None:
    """The horizon check is what makes a day safe; this is so the first run
    after midnight is not routinely the one that finds a transaction open."""
    with tempfile.TemporaryDirectory() as directory:
        exporter = FakeExporter(directory, max_days=1, tables=one_table())
        just_after_midnight = in_day(0, DAY + datetime.timedelta(days=1))
        exporter.run(now=just_after_midnight + datetime.timedelta(minutes=30))
        assert exporter.exported == []

        later = FakeExporter(directory, max_days=1, tables=one_table())
        later.run(now=just_after_midnight + SETTLE_DELAY)
        assert len(later.exported) == 1


@with_script
def test_write_horizon_sees_a_transaction_held_by_another_session(
    script: Script,
) -> None:
    engine = script.db_engines[read_only_bind_key(script)]
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
        exporter = Exporter(db, "/nonexistent")

        before = db.execute(sql.text("SELECT clock_timestamp()")).scalar_one()
        # Nothing older may already be holding the horizon down, or the rest of
        # the test would be measuring that instead.
        assert exporter.get_write_horizon() >= before

        with engine.connect() as other:
            other.execute(sql.text("SELECT 1"))
            other_start = other.execute(
                sql.text(
                    "SELECT xact_start FROM pg_stat_activity "
                    "WHERE pid = pg_backend_pid()"
                )
            ).scalar_one()
            assert exporter.get_write_horizon() <= other_start

        assert exporter.get_write_horizon() > other_start


@with_script
def test_write_horizon_is_not_held_back_by_autovacuum(script: Script) -> None:
    """Vacuum runs long on tables this size and cannot introduce a row with a
    past created, so it must not stall the feed."""
    engine = script.db_engines[read_only_bind_key(script)]
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
        assert (
            "backend_type <> 'autovacuum worker'" in export_module.WRITE_HORIZON_QUERY
        )
        horizon = Exporter(db, "/nonexistent").get_write_horizon()
        assert horizon.tzinfo is not None


@with_script
def test_export_refuses_to_run_without_pg_read_all_stats(script: Script) -> None:
    """Without it pg_stat_activity hides other sessions' xact_start, so the
    horizon query would see only this session and call every day settled."""
    engine = script.db_engines[read_only_bind_key(script)]
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as db:
        check_stats_privilege(db)  # the test user is a superuser

        db.exec_driver_sql("DROP ROLE IF EXISTS acoustid_export_test_role")
        db.exec_driver_sql("CREATE ROLE acoustid_export_test_role")
        try:
            db.exec_driver_sql("SET ROLE acoustid_export_test_role")
            with pytest.raises(ExportError, match="pg_read_all_stats"):
                check_stats_privilege(db)
        finally:
            db.exec_driver_sql("RESET ROLE")
            db.exec_driver_sql("DROP ROLE IF EXISTS acoustid_export_test_role")


@with_script
def test_link_tables_do_not_publish_their_surrogate_id(script: Script) -> None:
    """Nothing in the published data refers to it, and a merge can change which
    id a given pair has, so publishing it only invites consumers to key on
    something unstable."""
    insert_fixtures(script)
    with tempfile.TemporaryDirectory() as directory:
        run_export(
            script.db_engines[read_only_bind_key(script)],
            directory,
            max_days=1,
            now=NOW,
        )

        for name, natural_key in [
            ("track_mbid-update", ("track_id", "mbid")),
            ("track_puid-update", ("track_id", "puid")),
            ("track_meta-update", ("track_id", "meta_id")),
        ]:
            rows = read_export(directory, name)
            assert rows, name
            for row in rows:
                assert "id" not in row, name
                for column in natural_key:
                    assert column in row, (name, column)


@with_script
def test_ids_referenced_from_other_files_are_still_published(script: Script) -> None:
    """track.id, fingerprint.id and meta.id are join keys for the other files."""
    insert_fixtures(script)
    with tempfile.TemporaryDirectory() as directory:
        run_export(
            script.db_engines[read_only_bind_key(script)],
            directory,
            max_days=1,
            now=NOW,
        )

        assert all("id" in row for row in read_export(directory, "track-update"))
        assert all("id" in row for row in read_export(directory, "fingerprint-update"))
        assert all("id" in row for row in read_export(directory, "meta-update"))

        meta_ids = {row["id"] for row in read_export(directory, "meta-update")}
        track_meta = read_export(directory, "track_meta-update")
        assert {row["meta_id"] for row in track_meta} <= meta_ids
