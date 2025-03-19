import datetime
import logging

from flask import Blueprint, render_template, request
from sqlalchemy import sql
from sqlalchemy.orm import Bundle

from acoustid.models import Application, StatsLookups
from acoustid.web import db
from acoustid.web.utils import require_admin

logger = logging.getLogger(__name__)

admin_page = Blueprint("admin", __name__)


@admin_page.route("/admin")
def index():
    require_admin()
    return render_template("admin_index.html")


@admin_page.route("/admin/stats/apps")
def stats_apps():
    require_admin()

    last_months = [datetime.date.today().replace(day=1)]
    first_month = db.session.query(sql.func.min(StatsLookups.date)).scalar()
    if first_month is not None:
        first_month = first_month.replace(day=1)
        while last_months[-1] > first_month:
            month = last_months[-1] - datetime.timedelta(1)
            last_months.append(month.replace(day=1))

    month_str = request.args.get("month")
    if month_str:
        month = datetime.datetime.strptime(month_str, "%Y-%m").date()
    else:
        month = last_months[0]

    counts: Bundle[int] = Bundle(
        "counts",
        sql.func.sum(StatsLookups.count_hits).label("hits"),
        sql.func.sum(StatsLookups.count_nohits).label("misses"),
        sql.func.sum(StatsLookups.count_nohits + StatsLookups.count_hits).label("all"),
    )
    stats = (
        db.session.query(Application, counts)
        .join(StatsLookups.application)
        .filter(
            StatsLookups.date >= sql.func.date_trunc("month", month),
            StatsLookups.date
            < sql.func.date_trunc("month", month) + sql.text("INTERVAL '1 month'"),
        )
        .group_by(Application.id)
        .order_by(counts.c.all.desc())
        .all()
    )

    return render_template(
        "admin_stats_apps.html", stats=stats, last_months=last_months, month=month
    )
