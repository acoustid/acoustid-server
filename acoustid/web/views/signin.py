# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Signing in by email, with a link or a code."""

import logging
from typing import Any

from flask import (
    Blueprint,
    current_app,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.wrappers import Response

from acoustid.data.email import (
    SIGNIN_TTL,
    TooManyWrongCodes,
    UsedSignin,
    consume_email_signin_by_code,
    consume_email_signin_by_token,
    count_signin_email_sent,
    create_email_signin,
    find_or_create_email_account,
    get_email_signin_address,
    get_email_signin_by_token,
    mask_email,
    normalize_email,
    signin_allowed,
)
from acoustid.mail import MailError, send_mail
from acoustid.web import db
from acoustid.web.utils import is_our_url
from acoustid.web.views.user import (
    account_csrf_token,
    check_account_csrf_token,
    render_login_page,
)

logger = logging.getLogger(__name__)

signin_page = Blueprint("signin", __name__)

# The sign-in requests whose codes this browser may enter, newest last.
SIGNIN_SESSION_KEY = "email_signin_ids"
# Kept for asking again when the first email is slow to arrive.
MAX_SIGNINS_PER_SESSION = 3

INVALID_LINK = (
    "This sign-in link is not valid. It may have been used already, or "
    "expired. You can ask for a new one."
)


def private_page(body: str, status: int = 200) -> Response:
    """Pages with a token in the URL, or a button that signs in: no
    referrer, no framing."""
    response = make_response(body, status)
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    response.headers["X-Frame-Options"] = "DENY"
    return response


def secret() -> str:
    return current_app.config["SECRET_KEY"]


def sign_in(used: UsedSignin) -> Response:
    account_id = find_or_create_email_account(
        db.get_app_db(), used.email, request.remote_addr
    )
    db.session.commit()
    # A new session for the new identity: nothing from before signing in,
    # the CSRF token included, carries over.
    session.clear()
    session["id"] = account_id
    if used.return_url and is_our_url(used.return_url):
        return redirect(used.return_url, code=303)
    return redirect(url_for("user.api_key"), code=303)


@signin_page.route("/login/email", methods=["POST"])
def request_signin() -> Any:
    if "id" in session:
        return redirect(url_for("general.index"))
    check_account_csrf_token()
    entered = request.form.get("email", "")
    return_url = request.form.get("return_url") or None
    if return_url and not is_our_url(return_url):
        return_url = None
    email = normalize_email(entered)
    if email is None:
        return render_login_page(
            ["That does not look like an email address."], return_url, entered, 400
        )
    # The same answer whether or not an account has the address, so this
    # cannot be used to find out which addresses are registered. The first
    # limit is in Postgres and holds without redis; see signin_allowed.
    too_many = ["Too many emails sent. Try again in an hour."]
    if not signin_allowed(db.get_app_db(), email):
        return render_login_page(too_many, return_url, entered, 400)
    if not count_signin_email_sent(
        db.get_redis(), secret(), email, request.remote_addr or ""
    ):
        return render_login_page(too_many, return_url, entered, 400)
    signin = create_email_signin(db.get_app_db(), secret(), email, return_url)
    # Committed before sending: a link that arrives must work.
    db.session.commit()
    base_url = current_app.acoustid_config.website.base_url.rstrip("/")  # type: ignore
    context = dict(
        link=base_url + url_for(".signin_link", token=signin.token),
        code=signin.code,
        minutes=int(SIGNIN_TTL.total_seconds() // 60),
    )
    try:
        send_mail(
            current_app.acoustid_config.mail,  # type: ignore
            email,
            "Sign in to AcoustID",
            render_template("mail/signin.txt", **context),
            render_template("mail/signin.html", **context),
        )
    except MailError:
        return render_login_page(
            ["We could not send the email right now. Please try again later."],
            return_url,
            entered,
            400,
        )
    ids = signin_ids() + [signin.id]
    session[SIGNIN_SESSION_KEY] = ids[-MAX_SIGNINS_PER_SESSION:]
    return redirect(url_for(".signin_code"), code=303)


def code_page(email: str, error: str | None = None) -> Response:
    return private_page(
        render_template(
            "signin_code.html",
            title="Check your inbox",
            masked_email=mask_email(email),
            minutes=int(SIGNIN_TTL.total_seconds() // 60),
            error=error,
            csrf_token=account_csrf_token(),
        ),
        200 if error is None else 400,
    )


def signin_ids() -> list[int]:
    ids = session.get(SIGNIN_SESSION_KEY)
    return list(ids) if isinstance(ids, list) else []


def expired_request() -> Response:
    # The session is left alone. This is also what a second click on "Sign
    # in" gets after the first one signed in, and its response must not
    # overwrite the session the first one set.
    return render_login_page(
        [
            "That sign-in request has expired, or had too many wrong codes. "
            "Ask for a new email."
        ],
        None,
        status=400,
    )


@signin_page.route("/login/email/code")
def signin_code() -> Any:
    ids = signin_ids()
    if not ids:
        return redirect(url_for("user.login"))
    email = get_email_signin_address(db.get_app_db(), ids[-1])
    if email is None:
        return expired_request()
    return code_page(email)


@signin_page.route("/login/email/code", methods=["POST"])
def signin_code_post() -> Any:
    check_account_csrf_token()
    ids = signin_ids()
    if not ids:
        return redirect(url_for("user.login"))
    try:
        used = consume_email_signin_by_code(
            db.get_app_db(), secret(), ids, request.form.get("code", "")
        )
    except TooManyWrongCodes:
        email = get_email_signin_address(db.get_app_db(), ids[-1])
        if email is None:
            return expired_request()
        return code_page(
            email,
            "Too many wrong codes for this address today. "
            "Use the link in the email instead.",
        )
    if used is not None:
        return sign_in(used)
    # A wrong code was counted; keep the count.
    db.session.commit()
    email = get_email_signin_address(db.get_app_db(), ids[-1])
    if email is None:
        return expired_request()
    return code_page(email, "That code is not right. Check the email and try again.")


# Opening the link only shows a button. Mail scanners fetch every link in a
# message, and would use the link up before its owner got to it.
@signin_page.route("/login/email/link")
def signin_link() -> Response:
    token = request.args.get("token", "")
    email = get_email_signin_by_token(db.get_app_db(), token)
    return private_page(
        render_template(
            "signin_link.html",
            title="Sign in to AcoustID",
            token=token,
            masked_email=mask_email(email) if email else None,
            signed_in="id" in session,
            error=None if email else INVALID_LINK,
            csrf_token=account_csrf_token(),
        ),
        200 if email else 400,
    )


@signin_page.route("/login/email/link", methods=["POST"])
def signin_link_post() -> Any:
    check_account_csrf_token()
    used = consume_email_signin_by_token(db.get_app_db(), request.form.get("token", ""))
    if used is None:
        return private_page(
            render_template(
                "signin_link.html",
                title="Sign in to AcoustID",
                token="",
                masked_email=None,
                error=INVALID_LINK,
                csrf_token=account_csrf_token(),
            ),
            400,
        )
    return sign_in(used)
