
# Copyright (C) 2023 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import time
import json
import random
from typing import Dict, Union, Tuple

from redis import Redis

NUM_QUEUES = 256


def enqueue_task(redis: Redis, name: str, kwargs: Dict[str, Union[str, int, float]]) -> None:
    data = {
        'name': name,
        'kwargs': kwargs,
    }
    encoded_data = json.dumps(data).encode('utf-8')
    queue = hash(encoded_data) % NUM_QUEUES
    key = f'tasks:{queue:02x}'.encode('ascii')
    redis.rpush(key, encoded_data)


def dequeue_task(redis: Redis, timeout: float) -> Tuple[str, Dict[str, Union[str, int, float]]]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        queue = random.randrange(NUM_QUEUES)
        key = f'tasks:{queue:02x}'.encode('ascii')
        encoded_data = redis.lpop(key)
        if not encoded_data:
            continue
        encoded_data = encoded_data.decode('utf-8')
        data = json.loads(encoded_data)
        if 'name' not in data or 'kwargs' not in data:
            continue
        return data['name'], data['kwargs']
    raise TimeoutError()
