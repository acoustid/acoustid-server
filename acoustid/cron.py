# Copyright (C) 2019 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import time
import logging
import functools
from typing import Callable, Any
from schedule import Scheduler
from acoustid.script import Script
from acoustid.scripts.update_stats import run_update_stats
from acoustid.scripts.update_lookup_stats import run_update_lookup_stats
from acoustid.scripts.update_user_agent_stats import run_update_user_agent_stats
from acoustid.scripts.cleanup_perf_stats import run_cleanup_perf_stats
# from acoustid.scripts.merge_missing_mbids import run_merge_missing_mbids

logger = logging.getLogger(__name__)


def create_schedule(script):
    # type: (Script) -> Scheduler

    def wrap_job(func):
        # type: (Callable[[Script, Any, Any], None]) -> Callable[[], None]
        @functools.wraps(func)
        def wrapper():
            logger.info('Running %s', func.__name__)
            func(script, None, None)
        return wrapper

    schedule = Scheduler()
    schedule.every(3).to(9).minutes.do(wrap_job(run_update_lookup_stats))
    # schedule.every(55).to(65).minutes.do(wrap_job(run_merge_missing_mbids))
    schedule.every(23).to(25).hours.do(wrap_job(run_update_stats))
    schedule.every(23).to(25).hours.do(wrap_job(run_update_user_agent_stats))
    schedule.every(23).to(25).hours.do(wrap_job(run_cleanup_perf_stats))
    return schedule


def run_cron(script):
    # type: (Script) -> None
    schedule = create_schedule(script)
    logging.info('Cron job schedule:')
    for job in schedule.jobs:
        logging.info('%r', job)
    while True:
        schedule.run_pending()
        delay = schedule.idle_seconds
        if delay > 0:
            time.sleep(delay)
