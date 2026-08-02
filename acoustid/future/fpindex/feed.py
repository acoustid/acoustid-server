# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""The changelog feed fpindex nodes replicate from.

A separate ASGI app from the /v3 API on purpose. It is internal, and mixing it
into the public app would share a process and a connection pool between traffic
with nothing in common.

    GET /_changelog/{index}/{generation}?after=&max=

**The server never waits.** It answers with whatever is available right now and
tells the consumer how long to sleep before asking again (`retry_after_ms`).
There is no long poll and no `timeout_ms`. Three reasons, in order of how much
they matter:

  - Nothing can hold a PostgreSQL transaction across a wait, because there is no
    wait. Measured on PG 17.4: any transaction touching fpindex_changelog holds
    ACCESS SHARE on *every* partition (all partitions are locked at plan time,
    before pruning), so a request that waited with a transaction open would
    block the retention job's partition drop. Every drop attempt would collide,
    retention would silently stop progressing, and the only symptom would be the
    maintenance task logging lock timeouts.
  - Request lifetimes stay short, so nothing accumulates held connections.
  - Consumer pacing lives in one place. Slowing every node down is a server-side
    change, not a fleet redeploy.

LISTEN/NOTIFY would also work and is used elsewhere in the project, but it is
overkill here: at a few hundred inserts a minute, a sleep the server chooses is
as good and far less machinery.

**410 is load-bearing.** A consumer asking to resume from a position that has
aged out must get 410 Gone, which RemoteCoordinator turns into
error.BelowRetention and Replicator handles by bootstrapping from a peer snapshot
instead. Answer 200-with-no-entries there and the node sits quietly at a
position that will never advance, forever, with nothing to see.
"""

import logging

from sqlalchemy import sql
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

from acoustid.fingerprint import to_unsigned
from acoustid.future.fpindex.wire import (
    GENERATION,
    INDEX_NAME,
    changelog_response,
    encode,
    encode_bootstrap_chunk,
    encode_bootstrap_header,
    encode_meta,
    insert_change,
    meta_response,
)

logger = logging.getLogger(__name__)

MSGPACK_MEDIA_TYPE = "application/vnd.msgpack"

# Bound what a client can ask for, whatever it sends.
MAX_ENTRIES = 10000

# What to tell a caught-up consumer to wait. This is the whole knob for feed
# latency versus query load, and it is deliberately the server's to turn.
IDLE_RETRY_MS = 1000

# Told to a consumer that got a full batch: there is probably more waiting, so
# come straight back.
BUSY_RETRY_MS = 0

# Fingerprints read per transaction while streaming a bootstrap, unless the client
# asks otherwise ("?chunk="). Each chunk is its own short transaction, so nothing
# holds a snapshot open across a scan that reads roughly 10 KB per row -- about a
# terabyte at production scale.
BOOTSTRAP_CHUNK = 1000


def _int_param(request: Request, name: str, default: int, maximum: int) -> int:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(0, min(value, maximum))


async def _read_batch(engine, after: int, limit: int) -> list[tuple[int, int, list]]:
    async with engine.connect() as conn:
        result = await conn.execute(
            sql.text(
                """
                SELECT id, fingerprint_id, query
                FROM fpindex_changelog
                WHERE id > :after
                ORDER BY id
                LIMIT :limit
                """
            ),
            {"after": after, "limit": limit},
        )
        # to_unsigned, not list(): `query` is PostgreSQL integer[], which is
        # SIGNED, so every term with the top bit set comes back negative. The
        # index declares these u32 (acoustid-index src/change.zig), and decoding
        # a negative into u32 fails the whole batch with IntegerOverflow. Same
        # conversion fpstore.py already does on its way to the wire.
        return [(row.id, row.fingerprint_id, to_unsigned(row.query)) for row in result]


async def _last_deleted_id(engine) -> int | None:
    """The highest position retention has thrown away, or None if it never has.

    Read from fpindex_meta rather than inferred from the changelog, because
    `min(id)` of the changelog cannot answer the question. An EMPTY changelog is
    either a fresh install -- where replaying from the start is correct -- or a
    quiet period in which every partition aged out, where a consumer must be sent
    to a peer instead. Those need opposite answers and the table cannot tell them
    apart. fpindex_meta can: the row only exists once retention has actually
    dropped something.
    """
    async with engine.connect() as conn:
        result = await conn.execute(
            sql.text("SELECT last_deleted_id FROM fpindex_meta")
        )
        return result.scalar_one_or_none()


async def handle_read_changelog(request: Request) -> Response:
    index_name = request.path_params["index"]
    generation = request.path_params["generation"]

    # A mismatch means the consumer is following a different lineage. Saying so
    # is the point: silently serving this one's data would apply it to the wrong
    # index.
    if index_name != INDEX_NAME or generation != GENERATION:
        logger.warning(
            "changelog requested for unknown lineage %r/%r", index_name, generation
        )
        return Response(status_code=404)

    after = _int_param(request, "after", 0, 2**63 - 1)
    limit = _int_param(request, "max", MAX_ENTRIES, MAX_ENTRIES)

    engine = request.app.state.app_ctx.get_fingerprint_db()

    # Everything at or below last_deleted_id is gone. No `after > 0` exemption:
    # a new node starting at 0 cannot build a complete index from what is left
    # either, and serving it the remainder would bring it up quietly incomplete.
    last_deleted = await _last_deleted_id(engine)
    if last_deleted is not None and after < last_deleted:
        logger.info(
            "consumer at %d is below the retention floor %d; answering 410",
            after,
            last_deleted,
        )
        return Response(status_code=410)

    rows = await _read_batch(engine, after, limit)

    # A full batch means there is probably more behind it. `rows` first because
    # with max=0 an empty result is also "full" (0 == 0), which would tell the
    # consumer to come straight back for nothing.
    retry_after_ms = BUSY_RETRY_MS if rows and len(rows) == limit else IDLE_RETRY_MS

    return Response(
        content=encode(changelog_response(rows, retry_after_ms)),
        media_type=MSGPACK_MEDIA_TYPE,
    )


async def handle_read_meta(request: Request) -> Response:
    """The index-lifecycle feed.

    Not a side channel: Replicator.metaLoop is what creates the data consumers
    (it folds these ops per index and calls addConsumer), so without this a
    replica never learns any index exists and never opens a changelog consumer at
    all.

    Entirely static here -- one index, created once, never deleted -- so there is
    no table behind it. Add one when a second lineage is real; until then a table
    would only be a place for this to disagree with itself.
    """
    after = _int_param(request, "after", 0, 2**63 - 1)
    limit = _int_param(request, "max", MAX_ENTRIES, MAX_ENTRIES)

    response = meta_response(after, limit, IDLE_RETRY_MS)
    # The feed is fixed, so a caught-up consumer is caught up for good. Nothing
    # to hurry back for.
    return Response(
        content=encode_meta(response),
        media_type=MSGPACK_MEDIA_TYPE,
    )


async def handle_health(request: Request) -> Response:
    """Readiness, and it actually checks something.

    A handler that returns ready=True unconditionally is a check whose pass and
    fail look identical -- it reports the process as able to serve while every
    request it serves is failing. The only thing this app needs in order to
    answer is the fingerprint database, so that is what gets verified.

    Deliberately NOT a check on how far consumers have got, or on the retention
    margin: readiness must mean "can serve requests". Tying it to replication
    state would take the feed out of service exactly when nodes most need to
    reach it.
    """
    engine = request.app.state.app_ctx.get_fingerprint_db()
    try:
        async with engine.connect() as conn:
            await conn.execute(sql.text("SELECT 1"))
    except Exception:
        # Broad on purpose. A refused connection arrives as ConnectionRefusedError
        # -- an OSError from asyncpg, not wrapped in SQLAlchemyError -- so catching
        # the latter returned 500 in the one case this exists to report.
        logger.exception("health check failed: fingerprint database unreachable")
        return Response(
            b'{"ready":false}', status_code=503, media_type="application/json"
        )
    return Response(b'{"ready":true}', media_type="application/json")


async def _current_position(engine) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(
            sql.text("SELECT coalesce(max(id), 0) FROM fpindex_changelog")
        )
        return int(result.scalar_one())


async def _fingerprints_after(engine, after_id: int, limit: int):
    async with engine.connect() as conn:
        result = await conn.execute(
            sql.text(
                """
                SELECT id, acoustid_extract_query(fingerprint) AS query
                FROM fingerprint
                WHERE id > :after_id
                ORDER BY id
                LIMIT :limit
                """
            ),
            {"after_id": after_id, "limit": limit},
        )
        # Unsigned on the way out, exactly as in _read_batch. Bootstrap is where
        # this bites first: a new node has to finish it before it ever tails the
        # changelog, so a signed term here stops replication before it starts.
        return [(row.id, to_unsigned(row.query)) for row in result]


async def handle_bootstrap(request: Request) -> Response:
    """Stream the whole current corpus, for a node that has nothing.

    The changelog cannot serve this: it starts at the migration and only records
    submissions from then on, so replaying it from 0 builds an index missing every
    fingerprint that already existed.

    Not resumable. It runs once per cluster -- one node pays for it and the rest
    take a peer snapshot of the result -- so an interrupted run just starts over.
    The one parameter, `chunk`, tunes how many rows each transaction reads and
    therefore how the stream is framed into arrays; it cannot change which
    changes are streamed.

    Correct without holding a snapshot open, which is the part worth understanding.
    `position` is read first, then the table is scanned in chunks, each its own
    transaction:

      - a fingerprint that existed when `position` was read is still there when its
        chunk runs, because fingerprints are never deleted or updated, so the chunks
        cannot miss it,
      - anything inserted during the scan has a changelog row above `position`,
        including a straggler that took a low id and committed late into a range
        already scanned,
      - replaying from `position` afterwards covers every gap, and the overlap costs
        nothing because inserts are upserts by document id.

    That matters at 100M rows: a single REPEATABLE READ scan would hold the xmin
    horizon for the whole run and block vacuum database-wide.

    Streaming also gives backpressure for free. The next chunk is only read once the
    client has drained the last, so a slow node throttles the scan instead of
    pulling a terabyte through the primary's buffer cache as fast as it can.
    """
    index_name = request.path_params["index"]
    generation = request.path_params["generation"]
    if index_name != INDEX_NAME or generation != GENERATION:
        logger.warning(
            "bootstrap requested for unknown lineage %r/%r", index_name, generation
        )
        return Response(status_code=404)

    # Floored at 1 rather than _int_param's 0: LIMIT 0 reads no rows, which is
    # indistinguishable from the end of the table -- the stream would end after
    # the header, a silently empty bootstrap.
    chunk = max(1, _int_param(request, "chunk", BOOTSTRAP_CHUNK, MAX_ENTRIES))

    engine = request.app.state.app_ctx.get_fingerprint_db()
    position = await _current_position(engine)

    async def stream():
        last_id = 0
        streamed = 0
        while True:
            rows = await _fingerprints_after(engine, last_id, chunk)
            if not rows:
                break
            changes = []
            for fingerprint_id, query in rows:
                # An all-silence fingerprint extracts to nothing. Sending it would
                # add a document with no terms, which can never match.
                if query:
                    changes.append(insert_change(fingerprint_id, query))
                last_id = fingerprint_id
            # A chunk whose every row extracted to nothing stays off the wire:
            # an empty array is the terminator, and must mean nothing else.
            if changes:
                yield encode_bootstrap_chunk(changes)
            streamed += len(changes)
        yield encode_bootstrap_chunk([])
        logger.info(
            "bootstrap streamed %d fingerprints at position %d", streamed, position
        )

    return StreamingResponse(
        _prepend(encode_bootstrap_header(position), stream()),
        media_type=MSGPACK_MEDIA_TYPE,
    )


async def _prepend(head: bytes, rest):
    yield head
    async for chunk in rest:
        yield chunk


async def handle_refuse_write(request: Request) -> Response:
    """The write half of the coordinator protocol, answered with a refusal.

    This log has exactly one writer: the AFTER INSERT trigger on `fingerprint`.
    Entries appear because a submission was stored, and nothing arriving over HTTP
    can or should add to them. Index lifecycle is equally fixed -- one index,
    created once -- and retention belongs to the maintenance task, not to whoever
    happens to call.

    These routes exist precisely because they are refused. Without them the
    request lands on a route registered GET-only, Starlette answers 405,
    RemoteCoordinator.statusToError funnels every unrecognised status into
    error.CoordinatorError, and the node reports 503 Service Unavailable -- "try
    again later" for a condition that will never change, so a client retries
    forever. 403 says it is refused on purpose.

    Note the node has to learn to read that: statusToError maps 403 into the same
    CoordinatorError bucket today, so this only reads correctly once the client
    side gains a case for it.
    """
    logger.warning(
        "refusing %r %r: this feed is read-only, the changelog is written by "
        "the fingerprint trigger",
        request.method,
        request.url.path,
    )
    return Response(
        b'{"error":"read-only feed: the changelog is written by the fingerprint '
        b'trigger, not over HTTP"}',
        status_code=403,
        media_type="application/json",
    )


routes = [
    Route(
        "/_changelog/{index}/{generation:int}",
        handle_read_changelog,
        methods=["GET"],
    ),
    Route("/_meta", handle_read_meta, methods=["GET"]),
    Route(
        "/_bootstrap/{index}/{generation:int}",
        handle_bootstrap,
        methods=["GET"],
    ),
    Route("/health", handle_health, methods=["GET"]),
    # Every write route the protocol defines (acoustid-index
    # coordinator_server.zig registerRoutes), so a node gets a straight answer
    # rather than a routing accident.
    Route(
        "/_changelog/{index}/{generation:int}",
        handle_refuse_write,
        methods=["POST"],
    ),
    # These verbs must match the client's, or the request hits a route that does
    # not accept it and 405 becomes an opaque 503 again.
    Route("/_index/{index}", handle_refuse_write, methods=["PUT", "DELETE"]),
    Route(
        "/_truncate/{index}/{generation:int}",
        handle_refuse_write,
        methods=["POST"],
    ),
]


def create_feed_app(config_file: str | None = None, tests: bool = False) -> Starlette:
    """Also the uvicorn factory. Called with no arguments in production, where
    Config.load falls back to $ACOUSTID_CONFIG -- the same way the web and api
    apps get their configuration."""
    import functools

    from acoustid.config import Config
    from acoustid.future.api.app import app_lifespan

    config = Config.load(config_file, tests=tests)
    return Starlette(
        routes=routes,
        lifespan=functools.partial(app_lifespan, config),
    )


# api is on 3031 and web on 3032; this continues the sequence.
DEFAULT_PORT = 3033

# A string so uvicorn can re-import it per worker; a typo would only surface at
# deploy time, so a test resolves it.
APP_FACTORY = "acoustid.future.fpindex.feed:create_feed_app"


def run_feed_app(host: str, port: int, workers: int | None = None) -> None:
    import uvicorn

    uvicorn.run(
        APP_FACTORY,
        factory=True,
        host=host,
        port=port,
        workers=workers,
        # Leave logging to Script.setup_console_logging, which has already run.
        log_config=None,
    )
