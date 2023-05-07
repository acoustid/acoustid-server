# Copyright (C) 2023 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import json
import random
import time
from typing import Dict, Tuple, Union

from acoustid.script import ScriptContext

NUM_QUEUES = 256


def enqueue_task(
    ctx: ScriptContext, name: str, kwargs: Dict[str, Union[str, int, float]]
) -> None:
    data = {
        "name": name,
        "kwargs": kwargs,
    }
    encoded_data = json.dumps(data).encode("utf-8")
    queue = hash(encoded_data) % NUM_QUEUES
    key = f"tasks:{queue:02x}".encode("ascii")
    ctx.redis.rpush(key, encoded_data)
    if ctx.statsd is not None:
        ctx.statsd.incr(f"tasks_enqueued_total,task={name}")


def dequeue_task(
    ctx: ScriptContext, timeout: float
) -> Tuple[str, Dict[str, Union[str, int, float]]]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        queue = random.randrange(NUM_QUEUES)
        key = f"tasks:{queue:02x}".encode("ascii")
        encoded_data = ctx.redis.lpop(key)
        if not encoded_data:
            continue
        encoded_data = encoded_data.decode("utf-8")
        data = json.loads(encoded_data)
        name = data.get("name")
        kwargs = data.get("kwargs")
        if name is None:
            continue
        if kwargs is None:
            kwargs = {}
        if ctx.statsd is not None:
            ctx.statsd.incr(f"tasks_dequeued_total,task={name}")
        return name, kwargs
    raise TimeoutError()
