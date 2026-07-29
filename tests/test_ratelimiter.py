# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from unittest import mock

from acoustid.ratelimiter import RateLimiter


def test_seconds_until_next_step_rounds_up_to_the_bucket_boundary() -> None:
    # default interval 20 split into 4 steps, so buckets are 5 seconds wide
    limiter = RateLimiter(mock.Mock(), "rl")
    with mock.patch("acoustid.ratelimiter.time.time", return_value=100.0):
        assert 5 == limiter.seconds_until_next_step()
    with mock.patch("acoustid.ratelimiter.time.time", return_value=102.5):
        assert 3 == limiter.seconds_until_next_step()
    with mock.patch("acoustid.ratelimiter.time.time", return_value=104.9):
        assert 1 == limiter.seconds_until_next_step()


def test_seconds_until_next_step_is_never_zero_or_past_the_step() -> None:
    limiter = RateLimiter(mock.Mock(), "rl")
    step = limiter.interval / limiter.steps
    for tenths in range(0, 200):
        with mock.patch("acoustid.ratelimiter.time.time", return_value=tenths / 10.0):
            value = limiter.seconds_until_next_step()
            assert 1 <= value <= step
