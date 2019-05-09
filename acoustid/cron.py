# Copyright (C) 2019 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import time
import logging
from schedule import Scheduler
from acoustid.scripts.update_stats import main as update_stats_main
from acoustid.scripts.update_lookup_stats import main as update_lookup_stats_main
from acoustid.scripts.update_user_agent_stats import main as update_user_agent_stats_main
from acoustid.scripts.cleanup_perf_stats import main as cleanup_perf_stats_main
from acoustid.scripts.merge_missing_mbids import main as merge_missing_mbids_main

logger = logging.getLogger(__name__)


def wrap_job(func, script):
    logger.info('Running %s', func.__name__)
    func(script)


def create_schedule(script):
    schedule = Scheduler()
    # hourly jobs
    schedule.every(55).to(65).minute.do(wrap_job, merge_missing_mbids_main, script)
    schedule.every(55).to(65).minute.do(wrap_job, update_lookup_stats_main, script)
    # daily jobs
    schedule.every(23).to(25).hour.do(wrap_job, update_stats_main, script)
    schedule.every(23).to(25).hour.do(wrap_job, update_user_agent_stats_main, script)
    schedule.every(23).to(25).hour.do(wrap_job, cleanup_perf_stats_main, script)
    return schedule


def main(script, opt, args):
    schedule = create_schedule(script)
    while True:
        schedule.run_pending()
        time.sleep(schedule.idle_seconds())
