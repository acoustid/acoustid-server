# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from typing import Any, List, Tuple, cast
from unittest import mock

import pytest

from acoustid.api import errors
from acoustid.api.v2 import APIHandler


class FakeStatsd:
    def __init__(self) -> None:
        self.counters: List[str] = []

    def incr(self, name: str, count: int = 1) -> None:
        self.counters.append(name)


class FakeRateLimiter:
    """Rejects whichever bucket it is told to."""

    def __init__(self, reject: str) -> None:
        self.reject = reject

    def limit(self, bucket: str, key: str, rate: float) -> bool:
        return bucket == self.reject

    def seconds_until_next_step(self) -> int:
        return 5


def make_handler(
    reject: str, application_rate_limits: Any = None
) -> Tuple[APIHandler, FakeStatsd]:
    handler = cast(APIHandler, APIHandler.__new__(APIHandler))
    statsd = FakeStatsd()
    handler.ctx = mock.MagicMock()
    handler.ctx.statsd = statsd
    handler.ctx.config.rate_limiter.applications = application_rate_limits or {}
    handler.ctx.config.rate_limiter.global_rate_limit = 100.0
    handler.ctx.config.rate_limiter.ips = {}
    handler.rate_limiter = cast(Any, FakeRateLimiter(reject))
    return handler, statsd


def test_application_rejection_is_counted() -> None:
    handler, statsd = make_handler("app")

    with pytest.raises(errors.TooManyRequests):
        handler._rate_limit("1.2.3.4", 3494)

    assert statsd.counters == ["api.rate_limit_exceeded_total,bucket=app,app=3494"]


def test_ip_rejection_is_not_tagged_with_the_address() -> None:
    """The IP bucket is reached whenever the application has no configured
    limit of its own, so the application id is normally set here."""
    handler, statsd = make_handler("ip")

    with pytest.raises(errors.TooManyRequests):
        handler._rate_limit("1.2.3.4", 3494)

    assert statsd.counters == ["api.rate_limit_exceeded_total,bucket=ip,app=3494"]
    assert not any("1.2.3.4" in c for c in statsd.counters)


def test_global_rejection_is_counted() -> None:
    handler, statsd = make_handler("global")

    with pytest.raises(errors.TooManyRequests):
        handler._rate_limit("1.2.3.4", 3494)

    assert statsd.counters == ["api.rate_limit_exceeded_total,bucket=global,app=3494"]


@pytest.mark.parametrize("bucket", ["global", "ip"])
def test_rejection_without_an_application_is_still_tagged(bucket: str) -> None:
    """api.requests_total emits the literal app=None, so this one does too."""
    handler, statsd = make_handler(bucket)

    with pytest.raises(errors.TooManyRequests):
        handler._rate_limit("1.2.3.4", None)

    assert statsd.counters == [
        f"api.rate_limit_exceeded_total,bucket={bucket},app=None"
    ]


def test_nothing_is_counted_when_the_request_is_allowed() -> None:
    handler, statsd = make_handler("nothing")

    handler._rate_limit("1.2.3.4", 3494)

    assert statsd.counters == []


def test_rejection_is_not_logged_above_debug(caplog: pytest.LogCaptureFixture) -> None:
    from acoustid.ratelimiter import RateLimiter

    redis = mock.MagicMock()
    redis.incr.return_value = 10_000
    redis.get.return_value = b"0"

    limiter = RateLimiter(redis, "rl")
    with caplog.at_level(logging.INFO, logger="acoustid.ratelimiter"):
        assert limiter.limit("app", "3494", 1.0) is True

    assert caplog.records == []
