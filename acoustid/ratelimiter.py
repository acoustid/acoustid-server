# Copyright (C) 2013 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import time
import logging

logger = logging.getLogger(__name__)


class RateLimiter(object):

    def __init__(self, redis, prefix, interval=20, steps=4):
        self.redis = redis
        self.prefix = prefix
        self.interval = interval
        self.steps = steps

    def limit(self, bucket, key, rate):
        ts = int(self.steps * time.time() / self.interval)

        full_key = '%s:%s:%s:%s' % (self.prefix, bucket, key, ts)
        count = self.redis.incr(full_key)
        self.redis.expire(full_key, (self.steps + 1) * self.interval / self.steps)

        for i in range(1, self.steps):
            full_key_i = '%s:%s:%s:%s' % (self.prefix, bucket, key, ts - i)
            count += int(self.redis.get(full_key_i) or 0)

        if count > rate * self.interval:
            self.redis.decr(full_key)
            logger.info("Key %s:%s exceeded the rate limit of %s requests per %s seconds", bucket, key, rate * self.interval, self.interval)
            return True

        logger.debug("Key %s:%s had %s requests in the last %s seconds (rate %f)", bucket, key, count, self.interval, float(count) / self.interval)
        return False

