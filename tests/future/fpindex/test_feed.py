# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import msgspec
import pytest
from sqlalchemy import sql
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
