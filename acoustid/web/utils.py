import logging
import re
import urllib.parse as urlparse

from flask import abort, g, redirect, request, session, url_for

from acoustid.data.account import is_moderator
from acoustid.models import Account
from acoustid.web import db

logger = logging.getLogger(__name__)


def require_user():
    account_id = session.get("id")
    if account_id is None:
        return abort(redirect(url_for("user.login", return_url=request.url)))
    account = db.session.query(Account).get(account_id)
    if account is None:
        logger.warning("invalid account ID found in session: %r", account_id)
        del session["id"]
        return abort(redirect(url_for("user.login", return_url=request.url)))
    g.user = account
    return account


def require_moderator():
    """A logged-in user with a linked MusicBrainz account.

    The same gate the inline editing history uses. Note it is broader than it
    sounds: is_moderator() only asks whether the account has an mbuser, so
    this is "signed in via MusicBrainz" rather than a narrow privilege.
    """
    account = require_user()
    if not is_moderator(db.get_app_db(), account.id):
        raise abort(404)
    return account


def require_admin():
    account = require_user()
    if not account.is_admin:
        raise abort(404)
    return account


def is_valid_email(s):
    if re.match(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4}$", s, re.I):
        return True
    return False


def is_valid_url(s):
    url = urlparse.urlparse(s)
    if url.scheme in ("http", "https") and url.netloc:
        return True
    return False


def is_our_url(url):
    parsed = urlparse.urlparse(url)
    return parsed.netloc == request.host
