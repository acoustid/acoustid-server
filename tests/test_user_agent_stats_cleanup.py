# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime

from sqlalchemy import sql

import tests
from acoustid import const
from acoustid import tables as schema
from acoustid.cron import create_schedule
from acoustid.script import ScriptContext
from acoustid.scripts.update_user_agent_stats import run_cleanup_user_agent_stats
from acoustid.worker import TASKS
from tests import with_script_context

TODAY = datetime.date.today()
CUTOFF = TODAY - const.USER_AGENT_STATS_RETENTION


def row(date: datetime.date, ip: str = "127.0.0.1") -> dict:
    return {
        "date": date,
        "application_id": 1,
        "user_agent": "test/1.0",
        "ip": ip,
        "count": 1,
    }


@with_script_context
def test_cleanup_deletes_user_agent_stats_past_retention(ctx: ScriptContext) -> None:
    table = schema.stats_user_agents
    db = ctx.db.get_app_db()
    day = datetime.timedelta(days=1)
    db.execute(
        table.insert(),
        [
            row(CUTOFF - 10 * day),
            row(CUTOFF - 10 * day, ip="127.0.0.2"),
            row(CUTOFF - day),
            row(CUTOFF),
            row(TODAY),
        ],
    )
    ctx.db.session.commit()
    try:
        assert tests.script is not None
        run_cleanup_user_agent_stats(tests.script)
        db = ctx.db.get_app_db()
        dates = db.execute(sql.select(table.c.date).order_by(table.c.date))
        assert [r[0] for r in dates] == [CUTOFF, TODAY]
        # Nothing left to delete is not an error.
        run_cleanup_user_agent_stats(tests.script)
    finally:
        ctx.db.get_app_db().execute(table.delete())
        ctx.db.session.commit()


def test_user_agent_stats_cleanup_is_scheduled() -> None:
    assert TASKS["cleanup_user_agent_stats"] is run_cleanup_user_agent_stats
    assert tests.script is not None
    names = [job.job_func.__name__ for job in create_schedule(tests.script).jobs]
    assert "cleanup_user_agent_stats" in names
