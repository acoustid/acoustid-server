# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from typing import Any, List, cast
from unittest import mock

import pytest

from acoustid.data.fingerprint import FingerprintSearcher


class FakeStatsd:
    def __init__(self) -> None:
        self.counters: List[str] = []

    def incr(self, name: str, count: int = 1) -> None:
        self.counters.append(name)


class FakeFpstore:
    """An fpstore client that fails the way a failover makes it fail."""

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    def search(self, *args: Any, **kwargs: Any) -> Any:
        raise self.exc


# Called instead of search(): conftest patches SEARCH_ONLY_IN_DATABASE to True
# for the whole session, so search() always takes the database path in tests and
# a test driving it would quietly assert nothing about fpstore at all.
def search_via_fpstore(searcher: FingerprintSearcher) -> Any:
    return searcher._search_via_fpstore([1, 2, 3], 120)


def make_searcher(exc: BaseException, fast: bool, statsd: Any) -> FingerprintSearcher:
    return FingerprintSearcher(
        db=cast(Any, mock.MagicMock()),
        index_pool=cast(Any, mock.MagicMock()),
        fpstore=cast(Any, FakeFpstore(exc)),
        fast=fast,
        statsd=statsd,
    )


def test_masked_timeout_is_counted() -> None:
    """A fast-mode timeout is answered with "no match" rather than an error, so
    without this counter it is invisible outside a dip in match rate."""
    statsd = FakeStatsd()
    searcher = make_searcher(TimeoutError("deadline exceeded"), True, statsd)

    assert search_via_fpstore(searcher) == []

    assert statsd.counters == ["api.fpstore_masked_errors_total,cause=TimeoutError"]


def test_the_counter_is_labelled_by_exception_class_not_message() -> None:
    """Bounded cardinality: a message would carry ids and deadlines."""
    statsd = FakeStatsd()

    class UpstreamUnavailable(TimeoutError):
        pass

    searcher = make_searcher(
        UpstreamUnavailable("shard 7 at 10.0.0.1:6379"), True, statsd
    )
    search_via_fpstore(searcher)

    assert statsd.counters == [
        "api.fpstore_masked_errors_total,cause=UpstreamUnavailable"
    ]


def test_nothing_is_counted_when_the_error_is_not_masked() -> None:
    """Outside fast mode the timeout propagates, so it is already visible as an
    error and counting it here would double-count the same failure."""
    statsd = FakeStatsd()
    searcher = make_searcher(TimeoutError("deadline exceeded"), False, statsd)

    with pytest.raises(TimeoutError):
        search_via_fpstore(searcher)

    assert statsd.counters == []


def test_counting_is_skipped_without_statsd() -> None:
    """The searcher is also built without statsd, from the submission path."""
    searcher = make_searcher(TimeoutError("deadline exceeded"), True, None)

    assert search_via_fpstore(searcher) == []
