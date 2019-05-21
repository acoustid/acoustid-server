# Copyright (C) 2019 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import time
import logging
import functools
from schedule import Scheduler
from acoustid.scripts.update_stats import main as update_stats_main
from acoustid.scripts.update_lookup_stats import main as update_lookup_stats_main
from acoustid.scripts.update_user_agent_stats import main as update_user_agent_stats_main
from acoustid.scripts.cleanup_perf_stats import main as cleanup_perf_stats_main
from acoustid.scripts.merge_missing_mbids import main as merge_missing_mbids_main

logger = logging.getLogger(__name__)


def create_schedule(script):

    def wrap_job(func):
        @functools.wraps(func)
        def wrapper():
            logger.info('Running %s', func.__name__)
            func(script, None, None)
        return wrapper

    schedule = Scheduler()
    # hourly jobs
    schedule.every(55).to(65).minutes.do(wrap_job(merge_missing_mbids_main))
    schedule.every(55).to(65).minutes.do(wrap_job(update_lookup_stats_main))
    # daily jobs
    schedule.every(23).to(25).hours.do(wrap_job(update_stats_main))
    schedule.every(23).to(25).hours.do(wrap_job(update_user_agent_stats_main))
    schedule.every(23).to(25).hours.do(wrap_job(cleanup_perf_stats_main))
    return schedule


def run_cron(script):
    schedule = create_schedule(script)
    while True:
        schedule.run_pending()
        time.sleep(schedule.idle_seconds)
