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
from starlette.responses import Response
from starlette.routing import Route

from acoustid.future.fpindex.wire import (
    GENERATION,
    INDEX_NAME,
    changelog_response,
    encode,
    encode_meta,
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
        return [(row.id, row.fingerprint_id, list(row.query)) for row in result]


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
    generation = int(request.path_params["generation"])

    # A mismatch means the consumer is following a different lineage. Saying so
    # is the point: silently serving this one's data would apply it to the wrong
    # index.
    if index_name != INDEX_NAME or generation != GENERATION:
        logger.warning(
            "changelog requested for unknown lineage %s/%s", index_name, generation
        )
        return Response(status_code=404)

    after = _int_param(request, "after", 0, 2**63 - 1)
    limit = _int_param(request, "max", MAX_ENTRIES, MAX_ENTRIES) or MAX_ENTRIES

    engine = request.app.state.app_ctx.get_fingerprint_db()

    # Everything at or below last_deleted_id is gone, so a consumer whose next
    # wanted position (after + 1) falls in there cannot be served from the log.
    #
    # Deliberately no `after > 0` special case. A brand-new node starts at 0, and
    # if anything has been dropped it genuinely cannot build a complete index by
    # replaying what is left -- it has to bootstrap from a peer. Exempting 0 would
    # serve it a partial log as though it were the whole thing, and the index
    # would come up quietly incomplete.
    last_deleted = await _last_deleted_id(engine)
    if last_deleted is not None and after < last_deleted:
        logger.info(
            "consumer at %d is below the retention floor %d; answering 410",
            after,
            last_deleted,
        )
        return Response(status_code=410)

    rows = await _read_batch(engine, after, limit)

    # A full batch means there is probably more behind it; anything less means
    # the consumer is caught up as of this query.
    retry_after_ms = BUSY_RETRY_MS if len(rows) == limit else IDLE_RETRY_MS

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
    limit = _int_param(request, "max", MAX_ENTRIES, MAX_ENTRIES) or MAX_ENTRIES

    response = meta_response(after, limit, IDLE_RETRY_MS)
    # The feed is fixed, so a caught-up consumer is caught up for good. Nothing
    # to hurry back for.
    return Response(
        content=encode_meta(response),
        media_type=MSGPACK_MEDIA_TYPE,
    )


routes = [
    Route(
        "/_changelog/{index}/{generation:int}",
        handle_read_changelog,
        methods=["GET"],
    ),
    Route("/_meta", handle_read_meta, methods=["GET"]),
]


def create_feed_app(config_file: str | None = None, tests: bool = False) -> Starlette:
    import functools

    from acoustid.config import Config
    from acoustid.future.api.app import app_lifespan

    config = Config.load(config_file, tests=tests)
    return Starlette(
        routes=routes,
        lifespan=functools.partial(app_lifespan, config),
    )
