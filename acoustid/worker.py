# Copyright (C) 2023 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import contextvars
import logging
import time
from typing import Callable, Dict

import sentry_sdk

from acoustid.script import Script
from acoustid.scripts.merge_missing_mbids import run_merge_missing_mbid
from acoustid.scripts.update_lookup_stats import (
    run_update_all_lookup_stats,
    run_update_lookup_stats,
)
from acoustid.scripts.update_stats import run_update_stats
from acoustid.scripts.update_user_agent_stats import (
    run_update_all_user_agent_stats,
    run_update_user_agent_stats,
)
from acoustid.tasks import dequeue_task
from acoustid.tracing import initialize_trace_id

logger = logging.getLogger(__name__)


TaskFunc = Callable[..., None]

TASKS: Dict[str, TaskFunc] = {
    "update_stats": run_update_stats,
    "update_lookup_stats": run_update_lookup_stats,
    "update_all_lookup_stats": run_update_all_lookup_stats,
    "update_user_agent_stats": run_update_user_agent_stats,
    "update_all_user_agent_stats": run_update_all_user_agent_stats,
    "merge_missing_mbid": run_merge_missing_mbid,
}


def handle_task(script: Script, name: str, kwargs: dict) -> None:
    initialize_trace_id()

    func = TASKS.get(name)
    if func is None:
        logger.error("Unknown task: %s", name)
        return

    with script.context() as ctx:
        if ctx.statsd is not None:
            ctx.statsd.incr(f"tasks_started_total,task={name}")

    logger.info("Running task %s(%s)", name, kwargs)

    try:
        func(script, **kwargs)
    except Exception:
        logger.exception("Error running task: %s", name)
        sentry_sdk.capture_exception()
        return

    with script.context() as ctx:
        if ctx.statsd is not None:
            ctx.statsd.incr(f"tasks_finished_total,task={name}")

    logger.debug("Finished task %s(%s)", name, kwargs)


def run_worker(script: Script) -> None:
    script.setup_sentry(component="worker")
    logger.info("Starting worker")
    while True:
        with script.context() as ctx:
            started_at = time.time()
            while time.time() - started_at < 60:
                try:
                    name, kwargs = dequeue_task(ctx, timeout=10.0)
                except TimeoutError:
                    logger.debug("No tasks to run")
                    time.sleep(1.0)
                    continue

                cvctx = contextvars.copy_context()
                cvctx.run(handle_task, script, name, kwargs)
