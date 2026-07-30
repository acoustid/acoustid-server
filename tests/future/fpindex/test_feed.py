# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import msgspec
import pytest
from sqlalchemy import sql
from starlette.applications import Starlette
from starlette.testclient import TestClient

import tests
from acoustid.future.fpindex.feed import BUSY_RETRY_MS, IDLE_RETRY_MS
from acoustid.future.fpindex.wire import (
    GENERATION,
    INDEX_NAME,
    changelog_response,
    delete_change,
    encode,
    encode_meta,
    meta_response,
)

FEED = f"/_changelog/{INDEX_NAME}/{GENERATION}"

INSERT_FINGERPRINT = """
    INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
    VALUES (:fingerprint, 100, 1, 1)
    RETURNING id
"""


def _fingerprint(seed: int) -> list[int]:
    return [seed * 1000 + i for i in range(200)]


@pytest.fixture
def changelog():
    """A clean changelog, and a way to add to it through the real trigger."""
    assert tests.script is not None
    engine = tests.script.db_engines["fingerprint"]
    with engine.connect() as conn:
        conn.execute(sql.text("DELETE FROM fingerprint"))
        conn.execute(sql.text("DELETE FROM fpindex_changelog"))
        conn.execute(sql.text("DELETE FROM fpindex_meta"))
        conn.commit()
    yield engine
    with engine.connect() as conn:
        conn.execute(sql.text("DELETE FROM fingerprint"))
        conn.execute(sql.text("DELETE FROM fpindex_changelog"))
        conn.execute(sql.text("DELETE FROM fpindex_meta"))
        conn.commit()


def _add_fingerprint(engine, seed: int) -> int:
    with engine.connect() as conn:
        fingerprint_id = conn.execute(
            sql.text(INSERT_FINGERPRINT), {"fingerprint": _fingerprint(seed)}
        ).scalar_one()
        conn.commit()
    return fingerprint_id


def _positions(engine) -> list[int]:
    with engine.connect() as conn:
        return [
            row.id
            for row in conn.execute(
                sql.text("SELECT id FROM fpindex_changelog ORDER BY id")
            )
        ]


# --- wire format -------------------------------------------------------------
#
# These pin the structure the Zig client decodes, asserted against hand-written
# literals rather than round-tripped through the encoder -- a round-trip would
# pass just as happily if every key were wrong.


def test_read_response_uses_single_character_keys():
    payload = encode(changelog_response([(7, 42, [1, 2, 3])], 250))
    assert msgspec.msgpack.decode(payload) == {
        "e": [{"i": 7, "c": {"i": {"i": 42, "h": [1, 2, 3]}}}],
        "r": 250,
    }


def test_empty_read_response_still_carries_a_retry_hint():
    assert msgspec.msgpack.decode(encode(changelog_response([], 1000))) == {
        "e": [],
        "r": 1000,
    }


def test_delete_change_uses_its_own_union_tag():
    payload = msgspec.msgpack.encode(delete_change(42))
    assert msgspec.msgpack.decode(payload) == {"d": {"i": 42}}


# --- the endpoint ------------------------------------------------------------


def test_reads_entries_written_by_the_trigger(client: TestClient, changelog):
    fingerprint_id = _add_fingerprint(changelog, 1)

    response = client.get(FEED, params={"after": 0})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/vnd.msgpack")

    decoded = msgspec.msgpack.decode(response.content)
    assert len(decoded["e"]) == 1
    entry = decoded["e"][0]
    assert entry["i"] == _positions(changelog)[0]
    assert entry["c"]["i"]["i"] == fingerprint_id
    # The query terms, not the raw fingerprint.
    assert 0 < len(entry["c"]["i"]["h"]) <= 120


def test_after_resumes_and_does_not_repeat(client: TestClient, changelog):
    _add_fingerprint(changelog, 1)
    _add_fingerprint(changelog, 2)
    first, second = _positions(changelog)

    decoded = msgspec.msgpack.decode(client.get(FEED, params={"after": first}).content)
    assert [e["i"] for e in decoded["e"]] == [second]


def test_max_bounds_the_batch(client: TestClient, changelog):
    for seed in range(3):
        _add_fingerprint(changelog, seed)

    decoded = msgspec.msgpack.decode(
        client.get(FEED, params={"after": 0, "max": 2}).content
    )
    assert len(decoded["e"]) == 2


def test_caught_up_consumer_is_told_to_wait(client: TestClient, changelog):
    """The server answers immediately rather than holding the connection, so the
    retry hint is the only thing stopping the consumer from spinning."""
    decoded = msgspec.msgpack.decode(client.get(FEED, params={"after": 0}).content)
    assert decoded == {"e": [], "r": IDLE_RETRY_MS}
    assert IDLE_RETRY_MS > 0


def test_full_batch_tells_the_consumer_to_come_straight_back(
    client: TestClient, changelog
):
    """A full batch means there is probably more behind it, so sleeping would
    just add latency to catching up."""
    for seed in range(3):
        _add_fingerprint(changelog, seed)

    decoded = msgspec.msgpack.decode(
        client.get(FEED, params={"after": 0, "max": 2}).content
    )
    assert len(decoded["e"]) == 2
    assert decoded["r"] == BUSY_RETRY_MS


def test_partial_batch_means_caught_up(client: TestClient, changelog):
    _add_fingerprint(changelog, 1)

    decoded = msgspec.msgpack.decode(
        client.get(FEED, params={"after": 0, "max": 10}).content
    )
    assert len(decoded["e"]) == 1
    assert decoded["r"] == IDLE_RETRY_MS


def _record_retention_floor(engine, last_deleted_id: int) -> None:
    """Stand in for the maintenance job having dropped a partition."""
    with engine.connect() as conn:
        conn.execute(
            sql.text(
                """
                INSERT INTO fpindex_meta (
                    singleton, last_deleted_id, last_deleted_created,
                    last_deleted_xid
                )
                VALUES (true, :id, clock_timestamp(), pg_current_xact_id())
                ON CONFLICT (singleton) DO UPDATE
                    SET last_deleted_id = excluded.last_deleted_id
                """
            ),
            {"id": last_deleted_id},
        )
        conn.commit()


def test_below_retention_answers_410(client: TestClient, changelog):
    """The signal that makes a stuck node bootstrap from a peer.

    Without it the node would sit at a position that can never advance, quietly,
    which is the failure this status code exists to prevent.
    """
    _add_fingerprint(changelog, 1)
    _add_fingerprint(changelog, 2)
    first, _ = _positions(changelog)

    with changelog.connect() as conn:
        conn.execute(
            sql.text("DELETE FROM fpindex_changelog WHERE id <= :id"), {"id": first}
        )
        conn.commit()
    _record_retention_floor(changelog, first)

    assert client.get(FEED, params={"after": first - 1}).status_code == 410


def test_fully_expired_log_answers_410_not_an_empty_replay(
    client: TestClient, changelog
):
    """The case an earlier version of this got wrong, and had a passing test for.

    An empty changelog is ambiguous on its own -- fresh install, or every
    partition aged out. Inferring the floor from min(id) reads both as "nothing
    dropped", so a consumer whose position had expired got 200 with zero entries
    forever: a position it can never reach, no error, nothing to alert on. That is
    exactly the silent stall 410 exists to prevent. fpindex_meta is what makes the
    two distinguishable.
    """
    _record_retention_floor(changelog, 500)

    assert _positions(changelog) == []
    assert client.get(FEED, params={"after": 100}).status_code == 410


def test_fresh_install_replays_from_the_start(client: TestClient, changelog):
    """No retention has run, so there is no floor and nothing to be below."""
    assert client.get(FEED, params={"after": 5}).status_code == 200


def test_new_node_is_sent_to_a_peer_rather_than_served_a_partial_log(
    client: TestClient, changelog
):
    """A node starting at 0 cannot be exempted from the floor check.

    If anything has been dropped it cannot build a complete index from what is
    left, so serving it the remaining log would bring it up quietly incomplete.
    """
    _add_fingerprint(changelog, 1)
    _record_retention_floor(changelog, 500)

    assert client.get(FEED, params={"after": 0}).status_code == 410


def test_consumer_exactly_at_the_floor_is_still_served(client: TestClient, changelog):
    """after == last_deleted_id wants strictly newer positions, all of which are
    retained. Off-by-one here would send a healthy node for a needless snapshot."""
    _add_fingerprint(changelog, 1)
    floor = _positions(changelog)[0] - 1
    _record_retention_floor(changelog, floor)

    assert client.get(FEED, params={"after": floor}).status_code == 200


def test_unknown_lineage_is_rejected(client: TestClient, changelog):
    """A consumer on another lineage must not be fed this one's data."""
    assert client.get(f"/_changelog/{INDEX_NAME}/{GENERATION + 1}").status_code == 404
    assert client.get(f"/_changelog/other/{GENERATION}").status_code == 404


# --- the meta feed -----------------------------------------------------------


def test_meta_op_kind_is_an_integer_not_a_name():
    """msgpack.zig's packEnum writes @intFromEnum, so `create` is 0 on the wire.

    A string here would encode cleanly and never decode, which is the whole
    reason this is pinned rather than assumed.
    """
    decoded = msgspec.msgpack.decode(encode_meta(meta_response(0, 10, 1000)))
    assert decoded == {
        "o": [{"p": GENERATION, "k": 0, "i": INDEX_NAME}],
        "r": 1000,
    }


def test_meta_feed_announces_the_one_index(client: TestClient):
    decoded = msgspec.msgpack.decode(client.get("/_meta", params={"after": 0}).content)
    assert [op["i"] for op in decoded["o"]] == [INDEX_NAME]
    # A create's pos IS the generation, so a consumer reading this feed derives
    # exactly the generation the changelog route expects.
    assert decoded["o"][0]["p"] == GENERATION


def test_meta_feed_is_drained_once(client: TestClient):
    """metaLoop advances `after` past each op; once caught up it must stop
    getting the same create back, or it would reconcile forever."""
    decoded = msgspec.msgpack.decode(
        client.get("/_meta", params={"after": GENERATION}).content
    )
    assert decoded["o"] == []


# --- running it --------------------------------------------------------------


def test_health_reports_ready_when_the_database_answers(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ready": True}


def test_health_reports_unready_when_the_database_does_not(
    app: Starlette, client: TestClient, monkeypatch
):
    """A readiness check that cannot fail is not a check.

    Without this the handler could return ready=True while every request it
    serves is erroring, and nothing would take the process out of rotation.
    """

    class UnreachableEngine:
        def connect(self):
            # The real failure, taken from actually starting the service against
            # a database that was not listening. asyncpg raises this straight
            # through -- it is an OSError, NOT a SQLAlchemyError. An earlier
            # version of this test raised OperationalError instead and passed
            # while the handler returned 500 in production.
            raise ConnectionRefusedError(111, "Connection refused")

    # AsyncEngine.connect is read-only, so stand in a whole engine rather than
    # patching a method on the real one.
    monkeypatch.setattr(
        app.state.app_ctx,
        "get_fingerprint_db",
        lambda: UnreachableEngine(),
    )

    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"ready": False}


def test_health_reports_unready_on_a_sqlalchemy_error_too(
    app: Starlette, client: TestClient, monkeypatch
):
    """The other shape of database failure: a pool or dialect error that does
    arrive wrapped."""
    from sqlalchemy.exc import OperationalError

    class BrokenEngine:
        def connect(self):
            raise OperationalError("SELECT 1", {}, Exception("boom"))

    monkeypatch.setattr(app.state.app_ctx, "get_fingerprint_db", lambda: BrokenEngine())

    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"ready": False}


def test_uvicorn_factory_string_resolves():
    """APP_FACTORY is a string, so nothing checks it at import time.

    uvicorn re-imports it in every worker process; a typo would start the
    process, fail there, and only be visible in a deploy.
    """
    import importlib

    from acoustid.future.fpindex.feed import APP_FACTORY, create_feed_app

    module_name, _, attr = APP_FACTORY.partition(":")
    resolved = getattr(importlib.import_module(module_name), attr)
    assert resolved is create_feed_app
    assert callable(resolved)


def test_cli_exposes_the_feed_command():
    """`manage.py run fpindex-feed` is what admin/docker/run-fpindex-feed.sh
    calls, so the name has to exist."""
    from acoustid.cli import run

    assert "fpindex-feed" in run.commands


# --- refusing writes ---------------------------------------------------------


def test_every_write_route_is_refused_with_403(client: TestClient):
    """403, not 405 and not 503.

    The changelog has one writer -- the trigger on `fingerprint` -- so a write
    arriving over HTTP is refused permanently, and the status has to say so.
    Without these routes the request hits a GET-only route, Starlette answers 405,
    and the node's statusToError turns any unrecognised status into
    CoordinatorError, which it reports as 503: "try again later" for something that
    will never work.
    """
    attempts = [
        ("POST", f"/_changelog/{INDEX_NAME}/{GENERATION}"),  # append
        ("PUT", f"/_index/{INDEX_NAME}"),  # createIndex (idempotent -> PUT)
        ("DELETE", f"/_index/{INDEX_NAME}"),  # deleteIndex
        ("POST", f"/_truncate/{INDEX_NAME}/{GENERATION}"),  # setRetentionFloor
    ]
    for method, path in attempts:
        response = client.request(method, path)
        assert response.status_code == 403, f"{method} {path} -> {response.status_code}"
        assert "read-only" in response.json()["error"]


def test_refusing_a_write_does_not_shadow_the_read(client: TestClient, changelog):
    """The append and read routes share a path and differ only by method, so a
    mistake in registration order would break replication rather than writes."""
    assert client.get(FEED, params={"after": 0}).status_code == 200
    assert client.post(FEED).status_code == 403


def test_a_write_to_an_unknown_lineage_is_still_refused(client: TestClient):
    """The refusal is about the feed being read-only, not about the target, so it
    must not depend on the lineage matching."""
    assert client.post(f"/_changelog/other/{GENERATION + 5}").status_code == 403


# --- review findings ---------------------------------------------------------


def test_max_zero_is_honoured_not_turned_into_a_full_batch(
    client: TestClient, changelog
):
    """`max=0` used to be silently rewritten to MAX_ENTRIES.

    `_int_param` already substitutes the default when `max` is missing or
    unparsable, so a trailing `or MAX_ENTRIES` only ever caught an explicit zero --
    and answered with 10000 rows instead of none.
    """
    for seed in range(3):
        _add_fingerprint(changelog, seed)

    decoded = msgspec.msgpack.decode(
        client.get(FEED, params={"after": 0, "max": 0}).content
    )
    assert decoded["e"] == []


def test_max_zero_does_not_ask_the_consumer_to_come_straight_back(
    client: TestClient, changelog
):
    """The trap in honouring max=0: an empty result is also a "full" batch (0 == 0),
    which would answer BUSY_RETRY_MS -- come back immediately, for nothing. Only
    the client's own poll floor would stop it spinning."""
    for seed in range(3):
        _add_fingerprint(changelog, seed)

    decoded = msgspec.msgpack.decode(
        client.get(FEED, params={"after": 0, "max": 0}).content
    )
    assert decoded["r"] == IDLE_RETRY_MS
    assert decoded["r"] > 0


def test_meta_max_zero_is_honoured(client: TestClient):
    decoded = msgspec.msgpack.decode(client.get("/_meta", params={"max": 0}).content)
    assert decoded["o"] == []


def test_a_newline_in_the_index_name_cannot_forge_a_log_line(
    client: TestClient, caplog
):
    """ASGI hands over path params percent-decoded, so `%0a` in the URL arrives as
    a real newline. Logged with %s it would split one record into two."""
    import logging

    with caplog.at_level(logging.WARNING, logger="acoustid.future.fpindex.feed"):
        response = client.get(f"/_changelog/acoustid%0aforged/{GENERATION}")

    assert response.status_code == 404
    assert caplog.records, "expected the unknown-lineage warning"
    message = caplog.records[-1].getMessage()
    assert "\n" not in message, message
    assert "\\n" in message, message
