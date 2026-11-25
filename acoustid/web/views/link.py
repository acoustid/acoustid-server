# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Approving user keys that applications requested through the link flow."""

import hmac
import logging
import secrets
from typing import Any
from urllib.parse import urlparse

from flask import (
    Blueprint,
    abort,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from redis.exceptions import RedisError
from werkzeug.wrappers import Response

from acoustid.data.account import (
    approve_user_key_link_request,
    decline_user_key_link_request,
    format_link_code,
    get_pending_link_request,
    list_user_application_keys,
    normalize_link_code,
    refresh_cached_user_key,
    revoke_all_user_application_keys,
    revoke_user_application_key,
)
from acoustid.web import db
from acoustid.web.utils import require_user

logger = logging.getLogger(__name__)

link_page = Blueprint("link", __name__)

CSRF_TOKEN_KEY = "link_csrf_token"

# Wrong codes one account may try per hour. Per account rather than per
# session, because a session is a cookie the client can simply drop.
MAX_FAILED_CODES_PER_HOUR = 10

INVALID_CODE = "That code is not valid. It may have been used already, or expired."


def csrf_token() -> str:
    token = session.get(CSRF_TOKEN_KEY)
    if not token:
        token = session[CSRF_TOKEN_KEY] = secrets.token_urlsafe(32)
    return token


def check_csrf_token() -> None:
    token = session.get(CSRF_TOKEN_KEY)
    sent = request.form.get("csrf_token", "")
    if not token or not hmac.compare_digest(token, sent):
        abort(400)


def no_framing(body: str) -> Response:
    """A page with buttons that grant access must not be framed by another
    site that could trick someone into clicking them."""
    response = make_response(body)
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    response.headers["X-Frame-Options"] = "DENY"
    return response


def failed_code_attempts(account_id: int, increment: bool) -> int:
    key = "linkcode:fail:%d" % account_id
    redis = db.get_redis()
    try:
        if not increment:
            return int(redis.get(key) or 0)
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, 3600)
        return int(pipe.execute()[0])
    except RedisError:
        logger.warning("Failed to count link code attempts", exc_info=True)
        return 0


def return_host(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.netloc or None


def code_form(code: str = "", error: str | None = None) -> Response:
    return no_framing(
        render_template(
            "link_code.html", title="Connect an application", code=code, error=error
        )
    )


@link_page.route("/link")
def link() -> Response:
    user = require_user()
    code = request.args.get("code", "").strip()
    if not code:
        return code_form()
    if failed_code_attempts(user.id, increment=False) >= MAX_FAILED_CODES_PER_HOUR:
        return code_form(code, "Too many wrong codes. Try again in an hour.")
    pending = get_pending_link_request(db.get_app_db(), code)
    if pending is None:
        failed_code_attempts(user.id, increment=True)
        return code_form(code, INVALID_CODE)
    entered = request.args.get("entered") == "1"
    return no_framing(
        render_template(
            "link_consent.html",
            title="Connect %s?" % pending["application_name"],
            request_info=pending,
            code=format_link_code(normalize_link_code(code)),
            entered=entered,
            return_host=None if entered else return_host(pending["return_url"]),
            csrf_token=csrf_token(),
        )
    )


def decide(approve: bool) -> Any:
    user = require_user()
    check_csrf_token()
    code = request.form.get("code", "")
    entered = request.form.get("entered") == "1"
    app_db = db.get_app_db()
    pending = get_pending_link_request(app_db, code)
    if pending is None:
        return code_form(code, INVALID_CODE)
    if approve:
        apikey = approve_user_key_link_request(app_db, code, user.id)
    else:
        apikey = decline_user_key_link_request(app_db, code)
    if apikey is None:
        # Decided elsewhere between the two queries.
        return code_form(code, INVALID_CODE)
    db.session.commit()
    refresh_cached_user_key(db.get_redis(), db.get_app_db(), apikey)
    if pending["return_url"] and not entered:
        return redirect(pending["return_url"], code=303)
    return render_template(
        "link_done.html",
        title="Application connected" if approve else "Request declined",
        approved=approve,
        application_name=pending["application_name"],
    )


@link_page.route("/link/approve", methods=["POST"])
def approve() -> Any:
    return decide(approve=True)


@link_page.route("/link/decline", methods=["POST"])
def decline() -> Any:
    return decide(approve=False)


@link_page.route("/my-keys")
def my_keys() -> Response:
    user = require_user()
    keys = list_user_application_keys(db.get_app_db(), user.id)
    return no_framing(
        render_template(
            "my_keys.html",
            title="Connected applications",
            keys=keys,
            has_live_keys=any(k["revoked"] is None for k in keys),
            csrf_token=csrf_token(),
        )
    )


@link_page.route("/my-keys/revoke", methods=["POST"])
def revoke() -> Any:
    user = require_user()
    check_csrf_token()
    key_id = request.form.get("id", type=int)
    if key_id is None:
        abort(400)
    apikey = revoke_user_application_key(db.get_app_db(), key_id, user.id)
    db.session.commit()
    if apikey is not None:
        refresh_cached_user_key(db.get_redis(), db.get_app_db(), apikey)
    return redirect(url_for(".my_keys"), code=303)


@link_page.route("/my-keys/revoke-all", methods=["POST"])
def revoke_all() -> Any:
    user = require_user()
    check_csrf_token()
    apikeys = revoke_all_user_application_keys(db.get_app_db(), user.id)
    db.session.commit()
    for apikey in apikeys:
        refresh_cached_user_key(db.get_redis(), db.get_app_db(), apikey)
    return redirect(url_for(".my_keys"), code=303)
