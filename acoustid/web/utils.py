import re
import logging
import urlparse
from flask import request, redirect, url_for, abort, session, g
from acoustid.web import db
from acoustid.models import Account

logger = logging.getLogger(__name__)


def require_user():
    account_id = session.get('id')
    if account_id is None:
        return abort(redirect(url_for('user.login', return_url=request.url)))
    account = db.session.query(Account).get(account_id)
    if account is None:
        logger.warning('invalid account ID found in session: %r', account_id)
        del session['id']
        return abort(redirect(url_for('user.login', return_url=request.url)))
    g.user = account
    return account


def require_admin():
    account = require_user()
    if not account.is_admin:
        raise abort(404)
    return account


def is_valid_email(s):
    if re.match(r'^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4}$', s, re.I):
        return True
    return False


def is_valid_url(s):
    url = urlparse.urlparse(s)
    if url.scheme in ('http', 'https') and url.netloc:
        return True
    return False


def is_our_url(url):
    parsed = urlparse.urlparse(url)
    return parsed.netloc == request.host
