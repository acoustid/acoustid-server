"""Database statistics for the website, cached in Redis.

The home page, the about page and the statistics page all show the same
numbers. They change at most a few times a day, but the lookup statistics in
particular are an aggregate over a large table, so they are computed once and
shared by every page view for a while.
"""

import datetime
import json
import logging
from typing import Any, Callable

from acoustid.data.stats import find_current_stats, find_daily_stats, find_lookup_stats
from acoustid.web import db

logger = logging.getLogger(__name__)

# The totals are updated once a day and the lookup statistics only cover
# finished days, so a few minutes of staleness is never visible.
STATS_CACHE_TTL = datetime.timedelta(minutes=15)

CURRENT_STATS_KEY = "web:stats:current"
LOOKUP_STATS_KEY = "web:stats:lookups"
DAILY_ADDITIONS_KEY = "web:stats:additions"


# How long a request may hold the right to recompute a value, so a crashed
# request doesn't block the others for long.
LOCK_TTL = datetime.timedelta(seconds=60)


def cached_json(
    key: str,
    compute: Callable[[], Any],
    default: Any,
    ttl: datetime.timedelta = STATS_CACHE_TTL,
    single_flight: bool = False,
) -> Any:
    """The cached value of `compute()`, which has to return JSON-able data.

    Neither Redis nor the database failing may break the page: a problem with
    the cache is treated as a miss, and a failing `compute()` returns
    `default`, which is not cached, so the next request tries again.

    With `single_flight`, only one request at a time recomputes a missing
    value, and the others get `default` meanwhile. Use it when computing is
    expensive and `default` is a reasonable thing to show.
    """
    redis = None
    try:
        redis = db.get_redis()
        raw = redis.get(key)
    except Exception:
        logger.warning("Failed to read %s from the cache", key, exc_info=True)
        raw = None
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            logger.warning("Ignoring an unreadable cache entry for %s", key)

    lock_key = key + ":lock"
    if single_flight and redis is not None:
        try:
            locked = redis.set(
                lock_key, b"1", nx=True, ex=int(LOCK_TTL.total_seconds())
            )
        except Exception:
            locked = True
        if not locked:
            return default

    try:
        value = compute()
    except Exception:
        logger.warning("Failed to compute %s", key, exc_info=True)
        return default
    finally:
        if single_flight and redis is not None:
            try:
                redis.delete(lock_key)
            except Exception:
                pass

    try:
        db.get_redis().setex(key, int(ttl.total_seconds()), json.dumps(value))
    except Exception:
        logger.warning("Failed to write %s to the cache", key, exc_info=True)
    return value


def get_current_stats() -> dict[str, int]:
    """The latest totals, by stat name, such as "fingerprint.all"."""

    def compute() -> dict[str, int]:
        stats = find_current_stats(db.get_app_db())
        return {name: int(value or 0) for name, value in stats.items()}

    return cached_json(CURRENT_STATS_KEY, compute, default={})


def get_lookup_stats() -> list[dict[str, Any]]:
    """Searches per day over the last 30 days, with dates as ISO strings."""

    def compute() -> list[dict[str, Any]]:
        return [
            {
                "date": row["date"].isoformat(),
                "count": int(row["count"] or 0),
                "count_hits": int(row["count_hits"] or 0),
                "count_nohits": int(row["count_nohits"] or 0),
            }
            for row in find_lookup_stats(db.get_app_db())
        ]

    return cached_json(LOOKUP_STATS_KEY, compute, default=[])


def get_daily_additions() -> list[dict[str, Any]]:
    """New AcoustIDs and recordings per day, with dates as ISO strings."""

    def compute() -> list[dict[str, Any]]:
        rows = find_daily_stats(db.get_app_db(), ["track.all", "mbid.all"])
        return [
            {
                "date": row["date"].isoformat(),
                "track.all": int(row.get("track.all") or 0),
                "mbid.all": int(row.get("mbid.all") or 0),
            }
            for row in rows
        ]

    return cached_json(DAILY_ADDITIONS_KEY, compute, default=[])


def average_lookups(lookups: list[dict[str, Any]]) -> float:
    if not lookups:
        return 0
    return sum(d["count"] for d in lookups) / len(lookups)
