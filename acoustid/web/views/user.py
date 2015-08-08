import json
import base64
import urllib2
import logging
import random
from itsdangerous import URLSafeSerializer
from rauth import OAuth2Service
from openid import oidutil, fetchers
from openid.consumer import consumer as openid
from openid.extensions import ax, sreg
from flask import Blueprint, render_template, request, redirect, url_for, abort, current_app, session
from acoustid.web import db
from acoustid.web.utils import require_user, is_our_url
from acoustid.models import Account, AccountOpenID, AccountGoogle
from acoustid.utils import generate_api_key
from acoustid.data.account import (
    lookup_account_id_by_mbuser,
    lookup_account_id_by_openid,
    insert_account,
    get_account_details,
    reset_account_apikey,
    update_account_lastlogin,
    is_moderator,
)

logger = logging.getLogger(__name__)

user_page = Blueprint('user', __name__)


# monkey-patch uidutil.log to use the standard logging framework
openid_logger = logging.getLogger('openid')
def log_openid_messages(message, level=0):
    openid_logger.info(message)
oidutil.log = log_openid_messages


# force the use urllib2 with a timeout
fetcher = fetchers.Urllib2Fetcher()
fetcher.urlopen = lambda req: urllib2.urlopen(req, timeout=5)
fetchers.setDefaultFetcher(fetcher)


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
    return render_template('login.html', errors=errors,
        return_url=request.values.get('return_url'))


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


def login_user_and_redirect(user_id, return_url=None):
    session['id'] = user_id
    if not return_url:
        return_url = request.values.get('return_url')
    if return_url and is_our_url(return_url):
        return redirect(return_url)
    return redirect(url_for('general.index'))


def handle_musicbrainz_oauth2_login():
    musicbrainz = OAuth2Service(
        name='musicbrainz',
        client_id=current_app.config['MB_OAUTH_CLIENT_ID'],
        client_secret=current_app.config['MB_OAUTH_CLIENT_SECRET'],
        base_url='https://musicbrainz.org',
        authorize_url='https://musicbrainz.org/oauth2/authorize',
        access_token_url='https://musicbrainz.org/oauth2/token',
    )

    serializer = URLSafeSerializer(current_app.config['SECRET_KEY'])

    code = request.args.get('code')
    if not code:
        token = str(random.getrandbits(64))
        session['mb_login_token'] = token
        url = musicbrainz.get_authorize_url(**{
            'response_type': 'code',
            'scope': 'profile',
            'redirect_uri': url_for('.musicbrainz_login', _external=True),
            'state': serializer.dumps({
                'return_url': request.values.get('return_url'),
                'token': token,
            }),
        })
        return redirect(url)

    serialized_state = request.args.get('state')
    if serialized_state:
        state = serializer.loads(serialized_state)
    else:
        state = {}

    token = session.get('mb_login_token')
    if not token:
        raise Exception('token not found in session')

    if token != state.get('token'):
        raise Exception('token from session does not match token from oauth2 state')

    auth_session = musicbrainz.get_auth_session(data={
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': url_for('.musicbrainz_login', _external=True),
    }, decoder=json.loads)

    response = auth_session.get('oauth2/userinfo').json()

    user = find_or_create_musicbrainz_user(response['sub'])
    logger.info('MusicBrainz user %s "%s" logged in', user.id, user.name)

    return login_user_and_redirect(user.id, return_url=state.get('return_url'))


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


def handle_openid_login_request():
    openid_url = request.form['openid_identifier']
    try:
        consumer = openid.Consumer(session, None)
        openid_req = consumer.begin(openid_url)
    except openid.DiscoveryFailure:
        logger.exception('Error in OpenID discovery')
        raise
    else:
        if openid_req is None:
            raise Exception('No OpenID services found for the given URL')
        else:
            ax_req = ax.FetchRequest()
            ax_req.add(ax.AttrInfo('http://schema.openid.net/contact/email',
                      alias='email'))
            ax_req.add(ax.AttrInfo('http://axschema.org/namePerson/friendly',
                      alias='nickname'))
            openid_req.addExtension(ax_req)
            url = openid_req.redirectURL(get_openid_realm(),
                url_for('.openid_login', return_url=request.values.get('return_url'), _external=True))
            return redirect(url)
    raise Exception('OpenID login failed')


def handle_openid_login_response():
    conn = db.session.connection()
    consumer = openid.Consumer(session, None)
    info = consumer.complete(request.args, request.url)
    if info.status == openid.SUCCESS:
        openid_url = info.identity_url
        values = {}
        ax_resp = ax.FetchResponse.fromSuccessResponse(info)
        if ax_resp:
            attrs = {
                'email': 'http://schema.openid.net/contact/email',
                'name': 'http://schema.openid.net/namePerson/friendly',
            }
            for name, uri in attrs.iteritems():
                try:
                    value = ax_resp.getSingle(uri)
                    if value:
                        values[name] = value
                except KeyError:
                    pass
        account_id = lookup_account_id_by_openid(conn, openid_url)
        if not account_id:
            account_id, account_api_key = insert_account(conn, {
                'name': 'OpenID User',
                'openid': openid_url,
            })
        logger.info("Successfuly identified OpenID user %s (%d) with email '%s' and nickname '%s'",
            openid_url, account_id, values.get('email', ''), values.get('name', ''))
        return login_user_and_redirect(account_id)
    elif info.status == openid.CANCEL:
        raise Exception('OpenID login has been canceled')
    else:
        raise Exception('OpenID login failed')


def handle_openid_login():
    if 'openid.mode' in request.args:
        return handle_openid_login_response()
    else:
        return handle_openid_login_request()


@user_page.route('/login/openid')
def openid_login():
    try:
        response = handle_openid_login()
        db.session.commit()
    except Exception:
        logger.exception('OpenID login failed')
        db.session.rollback()
        return redirect(url_for('.login', error='OpenID login failed'))
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
    logger.info('Google user %s "%s" logged in', user.id, user.name)

    return login_user_and_redirect(user.id)


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
    return redirect(url_for('.api_key'))
