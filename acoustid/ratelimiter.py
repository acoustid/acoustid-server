# Copyright (C) 2013 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from __future__ import division

import logging
import math
import time

from redis import Redis

logger = logging.getLogger(__name__)


class RateLimiter(object):
    def __init__(self, redis, prefix, interval=20, steps=4):
        # type: (Redis, str, int, int) -> None
        self.redis = redis
        self.prefix = prefix
        self.interval = interval
        self.steps = steps

    def seconds_until_next_step(self):
        # type: () -> int
        """Seconds until the oldest step of the sliding window expires.

        The window is split into `steps` buckets keyed on absolute time, so
        capacity frees up when the current bucket rolls over. Rounded up, and
        never zero, so it can be used as a Retry-After value.
        """
        step = self.interval / self.steps
        return max(1, int(math.ceil(step - (time.time() % step))))

    def limit(self, bucket, key, rate):
        # type: (str, str, float) -> bool
        ts = int(self.steps * time.time() / self.interval)

        full_key = "%s:%s:%s:%s" % (self.prefix, bucket, key, ts)
        count = self.redis.incr(full_key)
        self.redis.expire(full_key, (self.steps + 1) * self.interval // self.steps)

        for i in range(1, self.steps):
            full_key_i = "%s:%s:%s:%s" % (self.prefix, bucket, key, ts - i)
            count += int(self.redis.get(full_key_i) or 0)

        if count > rate * self.interval:
            self.redis.decr(full_key)
            # Counted as api.rate_limit_exceeded_total by the caller.
            logger.debug(
                "Key %s:%s exceeded the rate limit of %s requests per %s seconds",
                bucket,
                key,
                rate * self.interval,
                self.interval,
            )
            return True

        logger.debug(
            "Key %s:%s had %s requests in the last %s seconds (rate %f)",
            bucket,
            key,
            count,
            self.interval,
            count / self.interval,
        )
        return False
