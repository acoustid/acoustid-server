import json
import base64
import logging
from rauth import OAuth2Service
from flask import Blueprint, render_template, request, redirect, url_for, abort, current_app, session
from acoustid.web import db
from acoustid.web.utils import require_user
from acoustid.models import Account, AccountOpenID, AccountGoogle
from acoustid.utils import generate_api_key

logger = logging.getLogger(__name__)

user_page = Blueprint('user', __name__)


@user_page.route('/login', methods=['GET', 'POST'])
def login():
    if 'id' in session:
        return redirect(url_for('general.index'))
    errors = list(request.args.getlist('error'))
    if request.method == 'POST':
        login_method = request.form.get('login')
        if login_method == 'musicbrainz':
            return musicbrainz_login()
        elif login_method == 'google':
            return google_login()
        elif login_method == 'openid':
            return openid_login()
    return render_template('login.html', errors=errors)


def find_or_create_musicbrainz_user(mb_user_name):
    user = db.session.query(Account).filter_by(mbuser=mb_user_name).first()
    if user is not None:
        return user

    user = Account()
    user.name = mb_user_name
    user.mbuser = mb_user_name
    user.apikey = generate_api_key()
    user.submission_count = 0
    db.session.add(user)
    db.session.flush()

    return user


def handle_musicbrainz_oauth2_login():
    musicbrainz = OAuth2Service(
        name='musicbrainz',
        client_id=current_app.config['MB_OAUTH_CLIENT_ID'],
        client_secret=current_app.config['MB_OAUTH_CLIENT_SECRET'],
        base_url='https://musicbrainz.org',
        authorize_url='https://musicbrainz.org/oauth2/authorize',
        access_token_url='https://musicbrainz.org/oauth2/token',
    )

    code = request.args.get('code')
    if not code:
        url = musicbrainz.get_authorize_url(**{
            'response_type': 'code',
            'scope': 'profile',
            'redirect_uri': url_for('.musicbrainz_login', _external=True),
        })
        return redirect(url)

    auth_session = musicbrainz.get_auth_session(data={
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': url_for('.musicbrainz_login', _external=True),
    }, decoder=json.loads)

    response = auth_session.get('oauth2/userinfo').json()

    user = find_or_create_musicbrainz_user(response['sub'])

    logger.info('MusicBrainz user %s "%s" logged in', user.id, user.name)
    session['id'] = user.id
    db.session.commit()

    return redirect(url_for('general.index'))


@user_page.route('/login/musicbrainz')
def musicbrainz_login():
    try:
        response = handle_musicbrainz_oauth2_login()
        db.session.commit()
    except Exception:
        logger.exception('MusicBrainz login failed')
        db.session.rollback()
        return redirect(url_for('.login', error='MusicBrainz login failed'))
    return response


def get_openid_realm():
    return url_for('general.index', _external=True).rstrip('/')


def find_or_create_google_user(google_user_id, openid=None):
    user = db.session.query(Account).join(AccountGoogle).\
        filter(AccountGoogle.google_user_id == google_user_id).first()
    if user is not None:
        return user

    if openid is not None:
        user = db.session.query(Account).join(AccountOpenID).\
            filter(AccountOpenID.openid == openid).first()
        if user is not None:
            db.session.query(AccountOpenID).\
                filter(AccountOpenID.openid == openid).delete()
            logger.info("Migrated OpenID user %s to Google user %s", openid, google_user_id)

    if user is None:
        user = Account()
        user.name = 'Google Account'
        user.apikey = generate_api_key()
        user.submission_count = 0
        db.session.add(user)
        db.session.flush()
        logger.info("Created user %s (%s)", user.id, user.name)

    google_user = AccountGoogle()
    google_user.account = user
    google_user.google_user_id = google_user_id
    db.session.add(google_user)
    logger.info("Associated user %s (%s) with Google user %s", user.id, user.name, google_user_id)

    return user


def handle_google_oauth2_login():
    google = OAuth2Service(
        name='google',
        client_id=current_app.config['GOOGLE_OAUTH_CLIENT_ID'],
        client_secret=current_app.config['GOOGLE_OAUTH_CLIENT_SECRET'],
        base_url='https://google.com',
        authorize_url='https://accounts.google.com/o/oauth2/auth',
        access_token_url='https://www.googleapis.com/oauth2/v3/token',
    )

    code = request.args.get('code')
    if not code:
        url = google.get_authorize_url(**{
            'response_type': 'code',
            'access_type': 'online',
            'scope': 'openid',
            'redirect_uri': url_for('.google_login', _external=True),
            'openid.realm': get_openid_realm(),
        })
        return redirect(url)

    response = json.loads(google.get_raw_access_token(data={
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': url_for('.google_login', _external=True),
    }).content)

    header, payload, secret = str(response['id_token']).split('.')
    payload += '=' * (4 - (len(payload) % 4))
    id_token = json.loads(base64.urlsafe_b64decode(payload))

    user = find_or_create_google_user(
        id_token['sub'], id_token.get('openid_id'))

    session['id'] = user.id
    logger.info('Google user %s "%s" logged in', user.id, user.name)

    return redirect(url_for('general.index'))


@user_page.route('/login/google')
def google_login():
    try:
        response = handle_google_oauth2_login()
        db.session.commit()
    except Exception:
        logger.exception('Google login failed')
        db.session.rollback()
        return redirect(url_for('.login', error='Google authentication failed'))
    return response


@user_page.route('/logout')
def logout():
    if 'id' in session:
        del session['id']
    return redirect(url_for('general.index'))


@user_page.route('/api-key')
def api_key():
    user = require_user()
    return render_template('apikey.html', title='Your API Key',
        apikey=user.apikey)


@user_page.route('/new-api-key')
def new_api_key():
    user = require_user()
    user.apikey = generate_api_key()
    db.session.commit()
    return redirect(url_for('user.api_key'))
