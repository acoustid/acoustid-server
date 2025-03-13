# Copyright (C) 2019 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
import time

import sentry_sdk
from schedule import Scheduler

from acoustid.script import Script
from acoustid.tasks import enqueue_task

logger = logging.getLogger(__name__)


def create_schedule(script: Script) -> Scheduler:
    def run_task(name: str, **kwargs: str | int | float):
        def wrapper() -> None:
            try:
                with script.context() as ctx:
                    enqueue_task(ctx, name, kwargs)
            except Exception:
                logger.exception("Error scheduling task: %s", name)
                sentry_sdk.capture_exception()

        wrapper.__name__ = name
        return wrapper

    schedule = Scheduler()
    schedule.every().minute.do(run_task("update_all_lookup_stats"))
    schedule.every().hour.do(run_task("update_all_user_agent_stats"))
    schedule.every().day.at("00:10").do(run_task("update_stats"))
    return schedule


def run_cron(script: Script) -> None:
    script.setup_sentry(component="cron")
    schedule = create_schedule(script)
    logging.info("Cron job schedule:")
    for job in schedule.jobs:
        logging.info("%r", job)
    while True:
        schedule.run_pending()
        delay = schedule.idle_seconds
        if delay > 0:
            time.sleep(delay)
