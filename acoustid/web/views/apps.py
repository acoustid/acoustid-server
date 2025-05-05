import json
import logging

from flask import (
    Blueprint,
    abort,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import sql
from werkzeug.wrappers import Response

from acoustid.data.application import (
    find_applications_by_account,
    insert_application,
    update_application,
)
from acoustid.data.stats import find_application_lookup_stats
from acoustid.web import db
from acoustid.web.utils import is_valid_email, is_valid_url, require_user

from .stats import prepare_chart_data

logger = logging.getLogger(__name__)

apps_page = Blueprint("apps", __name__)


@apps_page.route("/my-applications")
def applications() -> str:
    user = require_user()
    title = "Your Applications"
    applications = find_applications_by_account(db.get_app_db(), user.id)
    return render_template("applications.html", title=title, applications=applications)


@apps_page.route("/application/<int:application_id>")
def application(application_id: int) -> str:
    user = require_user()
    title = "Your Application"
    conn = db.get_app_db()
    application = conn.execute(
        sql.text(
            """
        SELECT * FROM application
        WHERE id = :application_id
    """
        ),
        {"application_id": application_id},
    ).fetchone()
    if application is None:
        abort(404)
    if user.id != application.account_id and not user.is_admin:
        abort(404)
    monthly_stats = conn.execute(
        sql.text(
            """
        SELECT
            date_trunc('month', date) AS month,
            sum(count_hits) + sum(count_nohits) AS lookups
        FROM stats_lookups
        WHERE application_id = :application_id
        GROUP BY date_trunc('month', date)
        ORDER BY date_trunc('month', date) DESC
    """
        ),
        {"application_id": application_id},
    ).fetchall()
    lookups = find_application_lookup_stats(conn, application_id)
    return render_template(
        "application.html",
        title=title,
        app=application,
        monthly_stats=monthly_stats,
        lookups=lookups,
        lookups_json=json.dumps(prepare_chart_data(lookups)),
    )


@apps_page.route("/new-application", methods=["GET", "POST"])
def new_application() -> str | Response:
    user = require_user()
    errors = []
    title = "New Application"
    if request.form.get("submit"):
        name = request.form.get("name")
        if not name:
            errors.append("Missing application name")
        version = request.form.get("version")
        if not version:
            errors.append("Missing version number")
        email = request.form.get("email")
        if not email:
            errors.append("Missing email address")
        if email and not is_valid_email(email):
            errors.append("Invalid email address")
        website = request.form.get("website")
        if website and not is_valid_url(website):
            errors.append("Invalid website URL")
        if not errors:
            insert_application(
                db.get_app_db(),
                {
                    "name": name,
                    "version": version,
                    "email": email,
                    "website": website,
                    "account_id": user.id,
                },
            )
            db.session.commit()
            return redirect(url_for(".applications"))
    return render_template(
        "new-application.html", title=title, form=request.form, errors=errors
    )


@apps_page.route("/application/<application_id>/edit", methods=["GET", "POST"])
def edit_application(application_id) -> str | Response:
    user = require_user()
    conn = db.get_app_db()
    application = conn.execute(
        sql.text(
            """
        SELECT * FROM application
        WHERE id = :app_id
    """
        ),
        {"app_id": application_id},
    ).fetchone()
    if application is None:
        abort(404)
    if user.id != application.account_id:
        abort(404)
    errors = []
    title = "Edit Application"
    if request.form.get("submit"):
        name = request.form.get("name")
        if not name:
            errors.append("Missing application name")
        version = request.form.get("version")
        if not version:
            errors.append("Missing version number")
        email = request.form.get("email")
        if email and not is_valid_email(email):
            errors.append("Invalid email address")
        website = request.form.get("website")
        if website and not is_valid_url(website):
            errors.append("Invalid website URL")
        if not errors:
            update_application(
                conn,
                application.id,
                {
                    "name": name,
                    "version": version,
                    "email": email,
                    "website": website,
                    "account_id": user.id,
                },
            )
            db.session.commit()
            return redirect(url_for(".application", application_id=application.id))
    else:
        form: dict[str, str] = {}
        form["name"] = application.name
        form["version"] = application.version or ""
        form["email"] = application.email or ""
        form["website"] = application.website or ""
    return render_template(
        "edit-application.html", title=title, form=form, errors=errors, app=application
    )
