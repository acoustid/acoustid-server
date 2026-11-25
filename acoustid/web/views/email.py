# Copyright (C) 2026 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

"""Adding or changing the email address on an account."""

import logging
from typing import Any

from flask import (
    Blueprint,
    abort,
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
    CONFIRMATION_TTL,
    consume_email_confirmation,
    count_email_sent,
    create_email_confirmation,
    get_email_confirmation,
    mask_email,
    normalize_email,
    set_account_email,
    within_global_limits,
)
from acoustid.mail import MailError, send_mail
from acoustid.models import Account
from acoustid.web import db
from acoustid.web.utils import require_user
from acoustid.web.views.user import (
    account_csrf_token,
    check_account_csrf_token,
    render_account_page,
    set_notice,
)

logger = logging.getLogger(__name__)

email_page = Blueprint("email", __name__)

INVALID_LINK = (
    "This confirmation link is not valid. It may have been used already, or "
    "expired. You can ask for a new one on your account page."
)


def signed_in_user(return_url: str) -> Account:
    """require_user, but returning somewhere a GET can go after signing in."""
    if "id" not in session:
        abort(redirect(url_for("user.login", return_url=return_url)))
    return require_user()


def private_page(body: str, status: int = 200) -> Response:
    """The confirmation page has the token in its URL, and a button that
    changes the account: no referrer, no framing."""
    response = make_response(body, status)
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
    response.headers["X-Frame-Options"] = "DENY"
    return response


def account_page_with_error(user: Account, email: str, error: str) -> Response:
    return render_account_page(user, email_value=email, email_error=error, status=400)


@email_page.route("/account/email", methods=["POST"])
def change_email() -> Any:
    user = signed_in_user(url_for("user.api_key", _external=True))
    check_account_csrf_token()
    entered = request.form.get("email", "")
    email = normalize_email(entered)
    if email is None:
        return account_page_with_error(
            user, entered, "That does not look like an email address."
        )
    if email == user.email:
        return account_page_with_error(
            user, entered, "That is already the address on your account."
        )
    # Whether another account already has the address is not checked here:
    # saying so would tell anyone with an account which addresses are
    # registered. Confirming the link is where it fails.
    secret = current_app.config["SECRET_KEY"]
    ip = request.remote_addr or ""
    mail_config = current_app.acoustid_config.mail  # type: ignore
    redis = db.get_redis()
    if not count_email_sent(redis, secret, user.id, email, ip) or not (
        within_global_limits(redis, mail_config.max_per_hour, mail_config.max_per_day)
    ):
        return account_page_with_error(
            user, entered, "Too many emails sent. Try again later."
        )
    token = create_email_confirmation(db.get_app_db(), user.id, email)
    # Committed before sending: a link that arrives must work.
    db.session.commit()
    # From the configured base URL, not the request: the Host header is the
    # client's to choose, and this link goes out in a genuine AcoustID email.
    base_url = current_app.acoustid_config.website.base_url.rstrip("/")  # type: ignore
    link = base_url + url_for(".confirm_email", token=token)
    context = dict(link=link, minutes=int(CONFIRMATION_TTL.total_seconds() // 60))
    try:
        send_mail(
            current_app.acoustid_config.mail,  # type: ignore
            email,
            "Confirm your email address for AcoustID",
            render_template("mail/confirm_email.txt", **context),
            render_template("mail/confirm_email.html", **context),
        )
    except MailError:
        # Caught here so the address never reaches an error report.
        return account_page_with_error(
            user,
            entered,
            "We could not send the email right now. Please try again later.",
        )
    set_notice("sent", email)
    return redirect(url_for("user.api_key"), code=303)


def confirm_page(error: str | None = None, **kwargs: Any) -> Response:
    return private_page(
        render_template(
            "email_confirm.html",
            title="Confirm your email address",
            error=error,
            csrf_token=account_csrf_token(),
            **kwargs,
        ),
        200 if error is None else 400,
    )


# Opening the link only shows a button. Mail scanners fetch every link in a
# message, and would use the link up before its owner got to it.
@email_page.route("/account/email/confirm")
def confirm_email() -> Response:
    token = request.args.get("token", "")
    user = require_user()
    confirmation = get_email_confirmation(db.get_app_db(), token)
    if confirmation is None:
        return confirm_page(INVALID_LINK)
    if confirmation.account_id != user.id:
        return confirm_page(
            "This link was sent for a different AcoustID account. Sign out, "
            "and sign in with the account you asked for it from."
        )
    return confirm_page(token=token, email=mask_email(confirmation.email))


@email_page.route("/account/email/confirm", methods=["POST"])
def confirm_email_post() -> Any:
    token = request.form.get("token", "")
    user = signed_in_user(url_for(".confirm_email", token=token, _external=True))
    check_account_csrf_token()
    app_db = db.get_app_db()
    # A link sent for another account is left alone, so it still works once
    # the right account is signed in.
    email = consume_email_confirmation(app_db, token, user.id)
    if email is None:
        return confirm_page(INVALID_LINK)
    if not set_account_email(app_db, user.id, email):
        # Rolls back the consumed link too, which is harmless: it would fail
        # the same way again.
        db.session.rollback()
        return confirm_page(
            "Another AcoustID account already uses this email address. "
            "Accounts are not merged; sign in to that account instead."
        )
    db.session.commit()
    set_notice("confirmed", email)
    return redirect(url_for("user.api_key"), code=303)
