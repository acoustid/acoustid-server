# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Rebuild the metadata search index.

One Typesense document per MusicBrainz recording, ranked at query time by text
match bucketed then by popularity, where popularity is the summed
`track_mbid.submission_count` of every AcoustID track mapped to that recording.
The design, the measurements behind it and the alternatives that were rejected
are in acoustid/acoustid-server#281.

The index is rebuilt in full rather than incrementally. A rebuild takes about
four minutes, and incremental updates could not be correct anyway:
`artist_credit` has no `last_updated`, deletions and MBID merges leave no
timestamp, and nothing maintains `track.updated`.

`track_mbid` lives on the fingerprint cluster and MusicBrainz on its own, with
no `postgres_fdw` or `dblink` between them, so no SQL join is possible. DuckDB
attaches both at once, which is the only reason it is here.

Postgres remains the source of truth. A bad index is repaired by rebuilding it,
so the index itself never needs backing up.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Any, Iterable, Iterator

import requests

from acoustid.script import Script

logger = logging.getLogger(__name__)

# Pinned deliberately. The extension cache path contains the DuckDB version, so
# an upgrade silently invalidates the copy baked into the image and the runtime
# falls back to downloading it -- or fails outright wherever egress is closed.
EXPECTED_DUCKDB_VERSION = "1.5.6"

COLLECTION_ALIAS = os.environ.get("TYPESENSE_COLLECTION_ALIAS", "mb_recordings")

# Where the swap marker is written. The alert that matters is not "did the job
# crash" -- a job that exits 0 having swapped nothing looks exactly like
# success -- it is "how long since a swap actually happened".
META_COLLECTION = "index_meta"
SWAP_MARKER_ID = "last_swap"

# A rebuild that produces far fewer documents than the one currently serving
# has gone wrong somewhere upstream, and must not replace it.
MIN_DOCUMENT_RATIO = 0.9

# Queries whose answers are known, checked against the new collection before
# the alias moves. Each is (query, expected artist, minimum popularity of the
# first hit). These are deliberately famous: if the join or the popularity sum
# broke, the top hit changes.
CANARY_QUERIES = [
    ("bohemian rhapsody", "Queen", 10000),
    ("yesterday", "The Beatles", 5000),
    ("smells like teen spirit", "Nirvana", 3000),
]

SEARCH_PARAMS = {
    "query_by": "name,artist,aliases",
    "query_by_weights": "3,2,1",
    "sort_by": "_text_match(buckets: 10):desc,popularity:desc",
    "prioritize_exact_match": "true",
}

COLLECTION_SCHEMA: dict[str, Any] = {
    "fields": [
        {"name": "name", "type": "string"},
        {"name": "artist", "type": "string"},
        {"name": "comment", "type": "string"},
        {"name": "aliases", "type": "string[]"},
        {"name": "length_ms", "type": "int32"},
        {"name": "popularity", "type": "int32"},
        {"name": "n_tracks", "type": "int32"},
    ],
    "default_sorting_field": "popularity",
}

# The whole pipeline in one statement.
#
# `gid_to_recording` is the union of live GIDs and redirected ones, which is
# what stops merged MBIDs being dropped: of 26.6M enabled mappings, 19,048
# only resolve through a redirect. The track page does the same thing one MBID
# at a time in resolve_mbid_redirect.
#
# Aliases are pre-aggregated per recording and per artist credit before being
# joined, rather than joined and then aggregated, so neither alias table
# multiplies the recording rows.
#
# Three-part naming throughout: the mirror is not in `public`.
DOCUMENTS_QUERY = """
WITH gid_to_recording AS (
    SELECT gid, id AS recording_id FROM mb.musicbrainz.recording
    UNION ALL
    SELECT gid, new_id AS recording_id FROM mb.musicbrainz.recording_gid_redirect
),
popularity AS (
    SELECT
        g.recording_id,
        sum(tm.submission_count)::BIGINT AS popularity,
        count(DISTINCT tm.track_id)::BIGINT AS n_tracks
    FROM fp.public.track_mbid tm
    JOIN gid_to_recording g ON g.gid = tm.mbid
    WHERE tm.disabled = false
    GROUP BY g.recording_id
),
recording_aliases AS (
    SELECT recording AS recording_id, list_distinct(list(name)) AS names
    FROM mb.musicbrainz.recording_alias
    GROUP BY recording
),
artist_aliases AS (
    SELECT acn.artist_credit, list_distinct(list(aa.name)) AS names
    FROM mb.musicbrainz.artist_credit_name acn
    JOIN mb.musicbrainz.artist_alias aa ON aa.artist = acn.artist
    GROUP BY acn.artist_credit
)
SELECT
    r.gid::VARCHAR AS id,
    r.name AS name,
    ac.name AS artist,
    r.comment AS comment,
    coalesce(r.length, 0)::INTEGER AS length_ms,
    coalesce(p.popularity, 0)::INTEGER AS popularity,
    coalesce(p.n_tracks, 0)::INTEGER AS n_tracks,
    list_distinct(
        list_concat(
            coalesce(ra.names, []::VARCHAR[]),
            coalesce(aa.names, []::VARCHAR[])
        )
    ) AS aliases
FROM mb.musicbrainz.recording r
JOIN mb.musicbrainz.artist_credit ac ON ac.id = r.artist_credit
LEFT JOIN popularity p ON p.recording_id = r.id
LEFT JOIN recording_aliases ra ON ra.recording_id = r.id
LEFT JOIN artist_aliases aa ON aa.artist_credit = r.artist_credit
ORDER BY popularity DESC
"""


class SearchIndexError(Exception):
    pass


def sql_literal(value: str) -> str:
    """A single-quoted SQL string.

    ATTACH, SET and COPY ... TO all take a literal rather than a placeholder in
    DuckDB, so these three have to be interpolated. The values are DSNs and
    temp paths from the environment rather than anything a request can reach,
    but quoting them is free.
    """
    return "'" + value.replace("'", "''") + "'"


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SearchIndexError(
            "%s is not set. The indexer is configured from the environment "
            "rather than acoustid.conf, because it needs pinned replica DSNs "
            "that do not go through pgbouncer." % (name,)
        )
    return value


def resolve_replica_dsn(patroni_url: str, database: str) -> str:
    """A DSN for one specific async replica of a Patroni cluster.

    Allow-listed on role == "replica" rather than excluding "leader", because
    Patroni also reports "sync_standby" and "standby_leader" and neither is
    safe to use. The sync standby sits in the primary's commit path, so a long
    analytical scan there slows down every write to the cluster -- and in this
    deployment the node this job is pinned to happens to be the sync standby
    for both clusters, which is exactly the member it must not read from.

    Pinning to a single instance is not an optimisation. DuckDB's parallel
    scanner calls pg_export_snapshot() on one connection and expects the next
    worker to reach the same backend; through a `-replicas` service the next
    worker lands on a different pod and the scan fails with "SET TRANSACTION
    SNAPSHOT ... snapshot does not exist".

    Resolved at runtime rather than configured, because leaders move every week
    or so and a hardcoded pod would quietly become the leader's.
    """
    response = requests.get(patroni_url.rstrip("/") + "/cluster", timeout=10)
    response.raise_for_status()
    members = response.json().get("members", [])
    replicas = [
        m for m in members if m.get("role") == "replica" and m.get("state") == "running"
    ]
    if not replicas:
        raise SearchIndexError(
            "No running async replica in the Patroni cluster at %s. "
            "Reading from the leader would work but is not what this job is "
            "for; fix the cluster rather than pointing the indexer at it."
            % (patroni_url,)
        )
    member = sorted(replicas, key=lambda m: m.get("name", ""))[0]
    host = member["host"]
    port = member.get("port", 5432)
    logger.info("Pinned to Patroni member %s (%s:%s)", member.get("name"), host, port)
    return "host=%s port=%s dbname=%s" % (host, port, database)


def connect_duckdb(temp_directory: str) -> Any:
    import duckdb

    if duckdb.__version__ != EXPECTED_DUCKDB_VERSION:
        # Not fatal: the pin exists so the baked extension matches, and a
        # mismatch means it will be downloaded instead. Worth saying loudly.
        logger.warning(
            "duckdb is %s, expected %s -- the extension baked into the image "
            "is version-specific, so this run may try to download it",
            duckdb.__version__,
            EXPECTED_DUCKDB_VERSION,
        )

    conn = duckdb.connect()
    # An in-memory connection has nowhere to spill and dies of OOM rather than
    # degrading, and this join does not fit in memory.
    conn.execute("SET temp_directory = " + sql_literal(temp_directory))
    conn.execute("SET preserve_insertion_order = false")
    # Deliberately far below what the machine has. This runs on the batch node
    # alongside production API pods, so the kernel's OOM killer is the thing to
    # stay away from; the node is short on RAM and enormous on disk, which is
    # the trade this job is configured for. Spilling is slower than the 229 s
    # measured on a 48 GB limit, and it completes.
    conn.execute(
        "SET memory_limit = "
        + sql_literal(os.environ.get("DUCKDB_MEMORY_LIMIT", "16GB"))
    )
    # Four parallel scans is already enough load on the replicas.
    conn.execute("SET threads = %d" % (int(os.environ.get("DUCKDB_THREADS", "4")),))
    extension_directory = os.environ.get("DUCKDB_EXTENSION_DIRECTORY")
    if extension_directory:
        # Explicit rather than $HOME: the workloads do not all run as the same
        # uid, so $HOME is not a stable location for a baked extension.
        conn.execute("SET extension_directory = " + sql_literal(extension_directory))
    conn.execute("INSTALL postgres")
    conn.execute("LOAD postgres")
    return conn


def export_documents(
    conn: Any, fingerprint_dsn: str, musicbrainz_dsn: str, path: str
) -> int:
    conn.execute(
        "ATTACH %s AS fp (TYPE postgres, READ_ONLY)" % (sql_literal(fingerprint_dsn),)
    )
    conn.execute(
        "ATTACH %s AS mb (TYPE postgres, READ_ONLY)" % (sql_literal(musicbrainz_dsn),)
    )
    logger.info("Exporting documents to %s", path)
    started = time.monotonic()
    conn.execute("COPY (%s) TO %s (FORMAT json)" % (DOCUMENTS_QUERY, sql_literal(path)))
    count = conn.execute(
        "SELECT count(*) FROM read_json_auto(%s)" % (sql_literal(path),)
    ).fetchone()[0]
    logger.info("Exported %d documents in %.1f s", count, time.monotonic() - started)
    return int(count)


class Typesense:
    def __init__(self, url: str, api_key: str) -> None:
        self.url = url.rstrip("/")
        self.headers = {"X-TYPESENSE-API-KEY": api_key}

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = requests.request(
            method, self.url + path, headers=self.headers, timeout=60, **kwargs
        )
        response.raise_for_status()
        return response.json() if response.content else None

    def collection_document_count(self, name: str) -> int | None:
        try:
            return int(self.request("GET", "/collections/" + name)["num_documents"])
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                return None
            raise

    def create_collection(self, name: str) -> None:
        self.request("POST", "/collections", json=dict(COLLECTION_SCHEMA, name=name))

    def import_documents(self, name: str, path: str) -> None:
        with open(path, "rb") as fileobj:
            response = requests.post(
                self.url + "/collections/" + name + "/documents/import",
                params={"action": "create"},
                headers=self.headers,
                data=fileobj,
                # The read has to be generous: Typesense indexes the whole
                # body before it answers, which measured 36 minutes for 23.3M
                # documents, and indexing the full catalogue would be more.
                # Two hours covers that with headroom and still bounds the
                # hang -- unbounded, a Typesense that stops answering wedges
                # the pod forever, and with concurrencyPolicy: Forbid that
                # takes every later rebuild down with it. The connect phase
                # has no reason to wait at all.
                timeout=(10, 7200),
            )
        response.raise_for_status()
        failures = [
            line
            for line in response.text.splitlines()
            if line and not json.loads(line).get("success")
        ]
        if failures:
            raise SearchIndexError(
                "%d document(s) failed to import, first: %s"
                % (len(failures), failures[0][:300])
            )

    def search(self, name: str, query: str, **params: Any) -> Any:
        return self.request(
            "GET",
            "/collections/" + name + "/documents/search",
            params=dict(SEARCH_PARAMS, q=query, **params),
        )

    def set_alias(self, alias: str, name: str) -> None:
        self.request("PUT", "/aliases/" + alias, json={"collection_name": name})

    def alias_target(self, alias: str) -> str | None:
        """The collection this alias points at, or None if it does not exist."""
        try:
            return str(self.request("GET", "/aliases/" + alias)["collection_name"])
        except requests.HTTPError as error:
            if error.response is not None and error.response.status_code == 404:
                return None
            raise

    def collections(self) -> list[dict[str, Any]]:
        return self.request("GET", "/collections") or []

    def drop_collection(self, name: str) -> None:
        self.request("DELETE", "/collections/" + name)


def check_canaries(typesense: Typesense, collection: str) -> None:
    """Refuse to swap in a collection that answers known queries wrongly.

    The failure being guarded against is an index that built and imported
    without error but is subtly wrong -- a join that lost its popularity, say
    -- swapping itself in and quietly degrading search for everyone. Same
    shape as the --max-delete guard on the backup sync.
    """
    for query, expected_artist, min_popularity in CANARY_QUERIES:
        hits = typesense.search(collection, query, per_page=1).get("hits", [])
        if not hits:
            raise SearchIndexError("Canary %r returned nothing" % (query,))
        document = hits[0]["document"]
        artist = document.get("artist")
        popularity = document.get("popularity", 0)
        if artist != expected_artist or popularity < min_popularity:
            raise SearchIndexError(
                "Canary %r returned %r by %r at popularity %s, expected %r "
                "at %s or more"
                % (
                    query,
                    document.get("name"),
                    artist,
                    popularity,
                    expected_artist,
                    min_popularity,
                )
            )
        logger.info(
            "Canary %r -> %r by %r (popularity %s)",
            query,
            document.get("name"),
            artist,
            popularity,
        )


def write_swap_marker(
    typesense: Typesense, collection: str, document_count: int, duration: float
) -> None:
    """Record that a swap happened, for something to alert on.

    KubeJobFailed cannot see a job that exits 0 having swapped nothing, so the
    thing worth alerting on is the age of this marker rather than the job's
    exit status.
    """
    if typesense.collection_document_count(META_COLLECTION) is None:
        typesense.request(
            "POST",
            "/collections",
            json={
                "name": META_COLLECTION,
                "fields": [
                    {"name": "collection", "type": "string"},
                    {"name": "swapped_at", "type": "int64"},
                    {"name": "documents", "type": "int32"},
                    {"name": "duration_s", "type": "float"},
                ],
            },
        )
    typesense.request(
        "POST",
        "/collections/%s/documents" % (META_COLLECTION,),
        params={"action": "upsert"},
        json={
            "id": SWAP_MARKER_ID,
            "collection": collection,
            "swapped_at": int(time.time()),
            "documents": document_count,
            "duration_s": round(duration, 1),
        },
    )


def obsolete_collections(
    typesense: Typesense, alias: str, keep: Iterable[str | None]
) -> Iterator[str]:
    """This alias's collections that nothing needs any more.

    `keep` holds the collection now serving plus the one that was serving
    before this run, so a bad swap can be undone by moving the alias back
    rather than waiting out a rebuild.

    Retaining by name order instead -- keep the newest besides the live one --
    is what this did first, and it was wrong. A run killed hard enough to skip
    its own cleanup strands a collection stamped later than any good one, which
    would then hold the rollback slot permanently while the last known-good
    copy was dropped out from under it every run.
    """
    kept = {name for name in keep if name}
    for collection in typesense.collections():
        name = collection["name"]
        if name.startswith(alias + "_") and name not in kept:
            yield name


def run_build_search_index(script: Script, opts: Any = None, args: Any = None) -> None:
    started = time.monotonic()

    typesense = Typesense(
        required_env("TYPESENSE_URL"), required_env("TYPESENSE_ADMIN_KEY")
    )

    patroni_fingerprint = os.environ.get("ACOUSTID_INDEX_FINGERPRINT_PATRONI_URL")
    patroni_musicbrainz = os.environ.get("ACOUSTID_INDEX_MUSICBRAINZ_PATRONI_URL")
    if patroni_fingerprint:
        fingerprint_dsn = resolve_replica_dsn(patroni_fingerprint, "acoustid")
    else:
        fingerprint_dsn = required_env("ACOUSTID_INDEX_FINGERPRINT_DSN")
    if patroni_musicbrainz:
        musicbrainz_dsn = resolve_replica_dsn(patroni_musicbrainz, "musicbrainz")
    else:
        musicbrainz_dsn = required_env("ACOUSTID_INDEX_MUSICBRAINZ_DSN")

    live_count = typesense.collection_document_count(COLLECTION_ALIAS)
    previous = typesense.alias_target(COLLECTION_ALIAS)
    collection = "%s_%d" % (COLLECTION_ALIAS, int(time.time()))

    with tempfile.TemporaryDirectory(prefix="search-index-") as workdir:
        path = os.path.join(workdir, "documents.ndjson")
        conn = connect_duckdb(workdir)
        try:
            count = export_documents(conn, fingerprint_dsn, musicbrainz_dsn, path)
        finally:
            conn.close()

        if live_count is not None and count < live_count * MIN_DOCUMENT_RATIO:
            raise SearchIndexError(
                "Built %d documents against %d currently serving, below the "
                "%.0f%% floor. Leaving the live collection alone."
                % (count, live_count, 100 * MIN_DOCUMENT_RATIO)
            )

        logger.info("Creating collection %s", collection)
        typesense.create_collection(collection)
        try:
            typesense.import_documents(collection, path)
            check_canaries(typesense, collection)
        except Exception:
            # The alias has not moved, so nothing is serving from this
            # collection, and a rebuild costs four minutes -- the half-built
            # copy is worth less than the disk it occupies. Dropping it here
            # bounds disk use at one collection however long a failure lasts;
            # left behind, an hourly job failing for a day would strand two
            # dozen full-size collections and the PVC filling up would then
            # break the recovery too. A hard kill skips this, which is what
            # the sweep at the end of a successful run is for.
            logger.error("Dropping failed collection %s", collection)
            typesense.drop_collection(collection)
            raise

    logger.info("Pointing alias %s at %s", COLLECTION_ALIAS, collection)
    typesense.set_alias(COLLECTION_ALIAS, collection)

    duration = time.monotonic() - started
    write_swap_marker(typesense, collection, count, duration)
    logger.info(
        "Swapped in %s with %d documents in %.1f s", collection, count, duration
    )

    # Past this point the new index is already serving and the marker is
    # written, so the build has succeeded whatever happens next. Letting a
    # failed delete propagate would exit non-zero and report that success as a
    # failure; the collection is merely left for the next run to sweep.
    for name in obsolete_collections(
        typesense, COLLECTION_ALIAS, (collection, previous)
    ):
        logger.info("Dropping superseded collection %s", name)
        try:
            typesense.drop_collection(name)
        except requests.RequestException:
            logger.exception("Could not drop superseded collection %s", name)
