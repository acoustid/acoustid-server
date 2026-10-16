# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Tests for the parts of the search indexer that fail silently.

The DuckDB export and the Typesense create/import/swap are not covered here:
they need two attached Postgres clusters and a Typesense instance, and were
verified by hand against a seeded fixture (redirected MBID, disabled mapping,
aliases from both tables) and against a real Typesense. What is covered is the
logic that would go wrong without anything crashing -- picking the wrong
Postgres instance, or deleting the wrong collection.
"""

from typing import Any
from unittest import mock

import pytest

from acoustid.scripts.build_search_index import (
    SearchIndexError,
    obsolete_collections,
    resolve_replica_dsn,
    sql_literal,
)


def member(
    name: str, role: str = "replica", state: str = "streaming"
) -> dict[str, Any]:
    """One entry as Patroni's /cluster endpoint reports it.

    The default state is "streaming", not "running". Patroni reports a
    non-leader's state from `replication_state` since 3.0.4, and "running" is
    what the leader reports -- a fixture using "running" for a replica
    describes a cluster that does not exist, which is how the code under test
    came to reject every healthy replica.
    """
    return {
        "name": name,
        "role": role,
        "state": state,
        "host": "%s.pg.svc" % (name,),
        "port": 5432,
    }


def as_collections(names: list[str]) -> list[dict[str, Any]]:
    return [{"name": name} for name in names]


def patroni_response(members: list[dict[str, Any]]) -> mock.Mock:
    response = mock.Mock()
    response.json.return_value = {"members": members}
    response.raise_for_status.return_value = None
    return response


def test_resolve_replica_dsn_never_returns_the_leader() -> None:
    """Reading from the leader is the one outcome that must not happen.

    The job exists to keep this load off the primary, and it would otherwise
    succeed quietly while doing exactly what it was meant to avoid.
    """
    members = [member("pg-0", role="leader", state="running"), member("pg-1")]
    with mock.patch("requests.get", return_value=patroni_response(members)):
        dsn = resolve_replica_dsn("http://patroni:8008", "acoustid")
    assert "pg-1" in dsn
    assert "pg-0" not in dsn


def test_resolve_replica_dsn_never_returns_the_sync_standby() -> None:
    """The sync standby sits in the primary's commit path.

    Excluding only the leader is not enough, and it is not a hypothetical: the
    node this job is pinned to is the sync standby for both clusters, so a
    blacklist of "leader" would have sent every build at the one member whose
    latency the primary waits on.
    """
    members = [
        member("pg-0", role="leader", state="running"),
        member("pg-1", role="sync_standby"),
        member("pg-2"),
    ]
    with mock.patch("requests.get", return_value=patroni_response(members)):
        dsn = resolve_replica_dsn("http://patroni:8008", "acoustid")
    assert "pg-2" in dsn


def test_resolve_replica_dsn_raises_when_only_a_sync_standby_is_available() -> None:
    """Better to skip a build than to run it against the commit path."""
    members = [
        member("pg-0", role="leader", state="running"),
        member("pg-1", role="sync_standby"),
    ]
    with mock.patch("requests.get", return_value=patroni_response(members)):
        with pytest.raises(SearchIndexError):
            resolve_replica_dsn("http://patroni:8008", "acoustid")


def test_resolve_replica_dsn_accepts_a_streaming_replica() -> None:
    """ "streaming" is what a healthy replica actually reports.

    This is the regression test for the inverted filter. The code accepted
    only state == "running", which a replica never reports on Patroni 3.0.4 or
    later -- so every member was rejected and the job raised instead of ever
    building an index. The one path the hand-verification could not cover,
    because it ran through the explicit-DSN fallback.
    """
    members = [member("pg-0", role="leader", state="running"), member("pg-1")]
    with mock.patch("requests.get", return_value=patroni_response(members)):
        dsn = resolve_replica_dsn("http://patroni:8008", "acoustid")
    assert "pg-1" in dsn


def test_resolve_replica_dsn_skips_a_replica_replaying_archived_wal() -> None:
    """ "in archive recovery" is not streaming, so it can lag arbitrarily."""
    members = [
        member("pg-0", role="leader", state="running"),
        member("pg-1", state="in archive recovery"),
        member("pg-2"),
    ]
    with mock.patch("requests.get", return_value=patroni_response(members)):
        dsn = resolve_replica_dsn("http://patroni:8008", "acoustid")
    assert "pg-2" in dsn


def test_resolve_replica_dsn_error_names_what_it_saw() -> None:
    """The message has to be diagnosable without cluster access.

    A bare "no healthy replica" against a cluster that plainly has replicas
    sends the reader to the wrong place. Naming each member's role and state
    is what would have identified the inverted filter immediately.
    """
    members = [
        member("pg-0", role="leader", state="running"),
        member("pg-1", state="in archive recovery"),
    ]
    with mock.patch("requests.get", return_value=patroni_response(members)):
        with pytest.raises(SearchIndexError) as caught:
            resolve_replica_dsn("http://patroni:8008", "acoustid")
    assert "pg-1=replica/in archive recovery" in str(caught.value)


def test_resolve_replica_dsn_is_stable_across_calls() -> None:
    """The same member every time, whatever order Patroni lists them in.

    DuckDB's parallel scanner calls pg_export_snapshot() on one connection and
    expects the next worker to reach the same backend, so a resolution that
    varied would reintroduce the bug that pinning exists to avoid.
    """
    forwards = [member("pg-1"), member("pg-2")]
    with mock.patch("requests.get", return_value=patroni_response(forwards)):
        first = resolve_replica_dsn("http://patroni:8008", "acoustid")
    with mock.patch("requests.get", return_value=patroni_response(forwards[::-1])):
        second = resolve_replica_dsn("http://patroni:8008", "acoustid")
    assert first == second


def test_resolve_replica_dsn_raises_when_every_member_is_the_leader() -> None:
    """A single-member cluster must stop the job, not silently use the leader."""
    members = [member("pg-0", role="leader")]
    with mock.patch("requests.get", return_value=patroni_response(members)):
        with pytest.raises(SearchIndexError):
            resolve_replica_dsn("http://patroni:8008", "acoustid")


def test_obsolete_collections_never_includes_the_live_collection() -> None:
    """Dropping the collection the alias points at would take search down.

    The live collection is deliberately NOT the newest here. An earlier version
    retained the newest collections by name and this case passed for the wrong
    reason -- the slice dropped the newest regardless of whether the live one
    was excluded on purpose, so the guard was untested.
    """
    typesense = mock.Mock()
    typesense.collections.return_value = as_collections(
        ["mb_recordings_300", "mb_recordings_400", "mb_recordings_500"]
    )
    result = list(
        obsolete_collections(typesense, "mb_recordings", ("mb_recordings_400", None))
    )
    assert "mb_recordings_400" not in result


def test_obsolete_collections_retains_the_previous_collection() -> None:
    """The collection that was serving stays, for an instant rollback."""
    typesense = mock.Mock()
    typesense.collections.return_value = as_collections(
        ["mb_recordings_%d" % n for n in (100, 200, 300, 400)]
    )
    result = list(
        obsolete_collections(
            typesense, "mb_recordings", ("mb_recordings_400", "mb_recordings_300")
        )
    )
    assert sorted(result) == ["mb_recordings_100", "mb_recordings_200"]


def test_obsolete_collections_drops_a_stray_newer_than_the_live_one() -> None:
    """A collection stranded by a hard kill must not become permanent.

    It carries a later timestamp than anything good, so retaining "the newest
    besides the live one" would have kept this forever and dropped the real
    previous collection in its place every single run.
    """
    typesense = mock.Mock()
    typesense.collections.return_value = as_collections(
        ["mb_recordings_300", "mb_recordings_400", "mb_recordings_999"]
    )
    result = list(
        obsolete_collections(
            typesense, "mb_recordings", ("mb_recordings_400", "mb_recordings_300")
        )
    )
    assert result == ["mb_recordings_999"]


def test_obsolete_collections_leaves_unrelated_collections_alone() -> None:
    """Only this alias's own collections are ours to delete.

    The index_meta collection holding the swap marker lives on the same
    instance, and a prefix match that caught it would delete the thing the
    staleness alert reads.
    """
    typesense = mock.Mock()
    typesense.collections.return_value = as_collections(
        ["mb_recordings_100", "mb_recordings_200", "index_meta", "mb_artists_100"]
    )
    result = list(
        obsolete_collections(typesense, "mb_recordings", ("mb_recordings_200", None))
    )
    assert "index_meta" not in result
    assert "mb_artists_100" not in result


def test_obsolete_collections_leaves_a_longer_alias_alone() -> None:
    """`mb_recordings_v2_100` belongs to a different alias, not to this one.

    A bare prefix test claims it, so the day a second alias is added under a
    name extending this one, this job would delete the other one's
    collections. Generated names are always `<alias>_<epoch>`.
    """
    typesense = mock.Mock()
    typesense.collections.return_value = as_collections(
        ["mb_recordings_100", "mb_recordings_200", "mb_recordings_v2_100"]
    )
    result = list(
        obsolete_collections(typesense, "mb_recordings", ("mb_recordings_200", None))
    )
    assert result == ["mb_recordings_100"]


def test_sql_literal_escapes_quotes() -> None:
    """The DSN is interpolated into ATTACH, which takes no placeholder."""
    assert sql_literal("pass'word") == "'pass''word'"
