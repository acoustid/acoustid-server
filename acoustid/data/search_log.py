# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Recording what people searched for, and which result they chose.

Deliberately not recorded: account ids and IP addresses. A query string
alongside either of those is personal data, and nothing here needs it. What
is recorded instead is an HMAC of an opaque token the client generates for
itself, keyed on a secret *and* the current UTC day -- so the same visitor
hashes to something different tomorrow and yesterday's rows cannot be
stitched into a history of one person. The secret is never stored beside the
hashes, and the day component means that even with the secret, re-identifying
a visitor requires knowing the token they had on that specific day.

What this is for is relevance: which queries return nothing, and which result
people actually pick when they do return something. Click position is the
useful part of that -- a query whose answer is reliably at position 7 is a
ranking problem, and nothing else in the system can see it.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import date, datetime, timezone

from sqlalchemy import sql

from acoustid import tables as schema
from acoustid.db import AppDB

logger = logging.getLogger(__name__)

# Enough to make collisions irrelevant at this volume, short enough not to
# look like something worth trying to reverse.
SESSION_HASH_LENGTH = 32


def hash_session_token(
    secret: str, token: str | None, today: date | None = None
) -> str | None:
    """An opaque, day-scoped hash of a client-supplied token.

    Returns None when there is no token or no secret to key with, which is a
    normal case rather than an error: the query still gets logged, just
    without a way to group it with anything else. Refusing to log without a
    token would quietly bias the data toward whichever visitors run
    JavaScript.

    The day is part of the message rather than the key so that rotation needs
    no stored state -- there is nothing to rotate, because the input changes
    on its own at midnight UTC.
    """
    if not token or not secret:
        return None
    if today is None:
        today = datetime.now(timezone.utc).date()
    digest = hmac.new(
        secret.encode("utf-8"),
        ("%s:%s" % (today.isoformat(), token)).encode("utf-8"),
        hashlib.sha256,
    )
    return digest.hexdigest()[:SESSION_HASH_LENGTH]


def insert_search_query(
    conn: AppDB, query: str, found: int, session: str | None = None
) -> int:
    """Record a search, returning the id a later click refers back to."""
    statement = (
        schema.search_query.insert()
        .values(query=query, found=found, session=session)
        .returning(schema.search_query.c.id)
    )
    return int(conn.execute(statement).scalar_one())


def insert_search_click(conn: AppDB, query_id: int, mbid: str, position: int) -> None:
    """Record which result was chosen, and where it sat in the list."""
    conn.execute(
        schema.search_click.insert().values(
            query_id=query_id, mbid=mbid, position=position
        )
    )


def delete_old_searches(conn: AppDB, before: datetime, limit: int) -> int:
    """Delete up to `limit` searches older than `before`, returning how many.

    Bounded per call so retention runs as a series of short transactions
    rather than one long one. A single unbounded DELETE over a quarter of the
    table would hold locks and a large transaction for as long as it took,
    on a cluster that is also serving the website.

    Clicks go with their query through ON DELETE CASCADE, so there is no
    second statement to keep in step and no way to leave orphans behind.
    """
    doomed = (
        sql.select(schema.search_query.c.id)
        .where(schema.search_query.c.created < before)
        .limit(limit)
    )
    result = conn.execute(
        schema.search_query.delete().where(schema.search_query.c.id.in_(doomed))
    )
    return int(result.rowcount)
