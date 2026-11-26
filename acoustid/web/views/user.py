import base64
import hmac
import json
import logging
import secrets
import urllib.request as urllib2
from typing import Any
from urllib.parse import urlparse

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
from itsdangerous import URLSafeSerializer
from openid import fetchers, oidutil
from openid.consumer import consumer as openid
from openid.extensions import ax
from rauth import OAuth2Service
from werkzeug.wrappers import Response

from acoustid.data.account import (
    insert_account,
    lookup_account_id_by_openid,
    refresh_cached_user_key,
)
from acoustid.data.email import (
    CONFIRMATION_TTL,
    mask_email,
    normalize_email,
    set_account_email,
)
from acoustid.models import Account, AccountGoogle, AccountOpenID
from acoustid.utils import generate_api_key
from acoustid.web import db
from acoustid.web.utils import is_our_url, require_user

logger = logging.getLogger(__name__)

user_page = Blueprint("user", __name__)


class LoginError(Exception):
    """A login attempt that failed for a reason the user can act on.

    These are expected in normal operation -- a mistyped identifier, a stale
    authorization code -- so they are logged at WARNING and turned into a
    message on the login page, rather than reported as server errors.
    """

    def __init__(self, message, log_message=None):
        super(LoginError, self).__init__(log_message or message)
        self.message = message


# monkey-patch uidutil.log to use the standard logging framework
openid_logger = logging.getLogger("openid")


def log_openid_messages(message, level=0):
    openid_logger.info(message)


oidutil.log = log_openid_messages


# force the use urllib2 with a timeout
fetcher = fetchers.Urllib2Fetcher()
fetcher.urlopen = lambda req: urllib2.urlopen(req, timeout=5)
fetchers.setDefaultFetcher(fetcher)


@user_page.route("/login", methods=["GET", "POST"])
def login():
    if "id" in session:
        return redirect(url_for("user.api_key"))
    errors = list(request.args.getlist("error"))
    if request.method == "POST":
        login_method = request.form.get("login")
        if login_method == "musicbrainz":
            return musicbrainz_login()
        elif login_method == "google":
            return google_login()
        elif login_method == "openid":
            return openid_login()
    return render_login_page(errors, request.values.get("return_url"))


def render_login_page(
    errors: list[str],
    return_url: str | None,
    email_value: str = "",
    status: int = 200,
) -> Response:
    body = render_template(
        "login.html",
        errors=errors,
        return_url=return_url,
        email_value=email_value,
        csrf_token=account_csrf_token(),
    )
    return make_response(body, status)


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
    session["id"] = user_id
    if not return_url:
        return_url = request.values.get("return_url")
    if return_url and is_our_url(return_url):
        return redirect(return_url)
    # The account page, as after an email sign-in: the key is what most
    # people sign in for.
    return redirect(url_for("user.api_key"))


def generate_login_token(session_key):
    """Make a CSRF token for an OAuth2 `state` parameter and remember it.

    `secrets` rather than `random`: the token only protects anything if the
    attacker cannot work out which value we are about to accept, and the
    Mersenne Twister behind `random` is reconstructible from its own output.
    """
    token = secrets.token_urlsafe(32)
    session[session_key] = token
    return token


def check_login_token(session_key, state):
    """Check an OAuth2 callback's `state` against the token in the session.

    Without this, anyone can send a victim's browser to our callback carrying
    an authorization code for the *attacker's* account -- the victim ends up
    silently signed in as someone else, and whatever they do next belongs to
    the attacker. A missing or mismatched token is rejected, never warned
    about and waved through.

    The token is dropped from the session either way, so a callback URL is
    good for one attempt and cannot be replayed out of somebody's history.
    """
    token = session.pop(session_key, None)
    if not token:
        raise LoginError(
            "Your sign-in session has expired. Please try again.",
            "no %s in the session to check the OAuth2 state against" % (session_key,),
        )
    if not state:
        raise LoginError(
            "Your sign-in session has expired. Please try again.",
            "no state in the OAuth2 callback to check %s against" % (session_key,),
        )
    if not hmac.compare_digest(token.encode("utf-8"), state.encode("utf-8")):
        raise LoginError(
            "Your sign-in session has expired. Please try again.",
            "%s does not match the state in the OAuth2 callback" % (session_key,),
        )


def handle_musicbrainz_oauth2_login():
    musicbrainz = OAuth2Service(
        name="musicbrainz",
        client_id=current_app.config["MB_OAUTH_CLIENT_ID"],
        client_secret=current_app.config["MB_OAUTH_CLIENT_SECRET"],
        base_url="https://musicbrainz.org",
        authorize_url="https://musicbrainz.org/oauth2/authorize",
        access_token_url="https://musicbrainz.org/oauth2/token",
    )

    serializer = URLSafeSerializer(current_app.config["SECRET_KEY"])

    code = request.args.get("code")
    if not code:
        token = generate_login_token("mb_login_token")
        url = musicbrainz.get_authorize_url(
            **{
                "response_type": "code",
                "scope": "profile",
                "redirect_uri": url_for(".musicbrainz_login", _external=True),
                "state": serializer.dumps(
                    {
                        "return_url": request.values.get("return_url"),
                        "token": token,
                    }
                ),
            }
        )
        return redirect(url)

    serialized_state = request.args.get("state")
    if serialized_state:
        state = serializer.loads(serialized_state)
    else:
        state = {}

    check_login_token("mb_login_token", state.get("token"))

    token_response = musicbrainz.get_raw_access_token(
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": url_for(".musicbrainz_login", _external=True),
        },
    )
    try:
        token = json.loads(token_response.content)
    except ValueError:
        raise LoginError(
            "MusicBrainz sign-in failed. Please try again.",
            "MusicBrainz token endpoint returned a non-JSON body (status=%r)"
            % (token_response.status_code,),
        )

    if "access_token" not in token:
        # MusicBrainz returns {"error": "invalid_grant"} for an authorization
        # code that was already used or has expired -- someone sitting on the
        # consent screen, going back, or reloading the callback. Asking rauth
        # for the token first turned that into a KeyError whose message was the
        # whole response body.
        #
        # The error and the keys only, never the body: a response without an
        # access_token can still carry one, and it must not reach the logs.
        raise LoginError(
            "Your MusicBrainz sign-in link has expired. Please try again.",
            "MusicBrainz token endpoint returned no access_token (error=%r, "
            "error_description=%r, keys=%r)"
            % (
                token.get("error"),
                token.get("error_description"),
                sorted(token),
            ),
        )

    auth_session = musicbrainz.get_session(token["access_token"])

    userinfo_response = auth_session.get("oauth2/userinfo")
    try:
        userinfo = userinfo_response.json()
    except ValueError:
        # An HTML error page, an empty body, or anything else that is not JSON.
        raise LoginError(
            "MusicBrainz sign-in failed. Please try again.",
            "MusicBrainz userinfo endpoint returned a non-JSON body (status=%r)"
            % (userinfo_response.status_code,),
        )

    if not userinfo.get("sub"):
        raise LoginError(
            "MusicBrainz sign-in failed. Please try again.",
            "MusicBrainz userinfo response carries no sub (keys=%r)"
            % (sorted(userinfo),),
        )

    user = find_or_create_musicbrainz_user(userinfo["sub"])
    logger.info('MusicBrainz user %s "%s" logged in', user.id, user.name)

    return login_user_and_redirect(user.id, return_url=state.get("return_url"))


@user_page.route("/login/musicbrainz")
def musicbrainz_login():
    try:
        response = handle_musicbrainz_oauth2_login()
        db.session.commit()
    except LoginError as e:
        logger.warning("MusicBrainz login failed: %s", e)
        db.session.rollback()
        return redirect(url_for(".login", error=e.message))
    except Exception:
        logger.exception("MusicBrainz login failed")
        db.session.rollback()
        return redirect(url_for(".login", error="MusicBrainz login failed"))
    return response


def validate_openid_identifier(openid_url):
    """Reject identifiers that cannot possibly be OpenID URLs.

    python-openid prepends "http://" to anything without a scheme, so a bare
    username becomes http://username/ and an email address becomes
    http://user@example.com/ -- both fail DNS resolution deep inside the
    fetcher. Catch them here, where we can still say something useful.
    """
    openid_url = openid_url.strip()
    if not openid_url:
        raise LoginError("Please enter your OpenID URL.")
    if "@" in openid_url:
        raise LoginError(
            "That looks like an email address. OpenID needs the URL of your "
            "OpenID provider, for example https://example.com/openid."
        )
    url = openid_url if "://" in openid_url else "http://" + openid_url
    try:
        hostname = urlparse(url).hostname or ""
    except ValueError:
        # urlparse raises on unbalanced square brackets ("Invalid IPv6 URL").
        hostname = ""
    if "." not in hostname.strip("."):
        raise LoginError(
            "That does not look like an OpenID URL. It should be a full "
            "address, for example https://example.com/openid."
        )
    return openid_url


def handle_openid_login_request():
    openid_url = validate_openid_identifier(request.form.get("openid_identifier", ""))
    try:
        consumer = openid.Consumer(session, None)
        openid_req = consumer.begin(openid_url)
    except openid.DiscoveryFailure as e:
        raise LoginError(
            "We could not find an OpenID provider at that address.",
            "OpenID discovery failed for %r: %s" % (openid_url, e),
        )
    else:
        if openid_req is None:
            raise LoginError(
                "We could not find an OpenID provider at that address.",
                "No OpenID services found for %r" % (openid_url,),
            )
        else:
            ax_req = ax.FetchRequest()
            ax_req.add(
                ax.AttrInfo("http://schema.openid.net/contact/email", alias="email")
            )
            ax_req.add(
                ax.AttrInfo("http://axschema.org/namePerson/friendly", alias="nickname")
            )
            openid_req.addExtension(ax_req)
            url = openid_req.redirectURL(
                get_openid_realm(),
                url_for(
                    ".openid_login",
                    return_url=request.values.get("return_url"),
                    _external=True,
                ),
            )
            return redirect(url)
    raise Exception("OpenID login failed")


def handle_openid_login_response():
    conn = db.get_app_db()
    consumer = openid.Consumer(session, None)
    info = consumer.complete(request.args, request.url)
    if info.status == openid.SUCCESS:
        openid_url = info.identity_url
        values = {}
        ax_resp = ax.FetchResponse.fromSuccessResponse(info)
        if ax_resp:
            attrs = {
                "email": "http://schema.openid.net/contact/email",
                "name": "http://schema.openid.net/namePerson/friendly",
            }
            for name, uri in attrs.items():
                try:
                    value = ax_resp.getSingle(uri)
                    if value:
                        values[name] = value
                except KeyError:
                    pass
        account_id = lookup_account_id_by_openid(conn, openid_url)
        if not account_id:
            account_id, account_api_key = insert_account(
                conn,
                {
                    "name": "OpenID User",
                    "openid": openid_url,
                },
            )
        # Not the email address: addresses sign people in now, and stay out
        # of the logs.
        logger.info(
            "Successfully identified OpenID user %s (%d)", openid_url, account_id
        )
        return login_user_and_redirect(account_id)
    elif info.status == openid.CANCEL:
        raise LoginError("OpenID login was canceled.")
    else:
        raise LoginError(
            "OpenID login failed.",
            "OpenID login failed with status %r: %s"
            % (info.status, getattr(info, "message", None)),
        )


def handle_openid_login():
    if "openid.mode" in request.args:
        return handle_openid_login_response()
    else:
        return handle_openid_login_request()


@user_page.route("/login/openid")
def openid_login():
    try:
        response = handle_openid_login()
        db.session.commit()
    except LoginError as e:
        logger.warning("OpenID login failed: %s", e)
        db.session.rollback()
        return redirect(url_for(".login", error=e.message))
    except Exception:
        logger.exception("OpenID login failed")
        db.session.rollback()
        return redirect(url_for(".login", error="OpenID login failed"))
    return response


def get_openid_realm():
    return url_for("general.index", _external=True).rstrip("/")


def find_or_create_google_user(google_user_id, openid=None):
    user = (
        db.session.query(Account)
        .join(AccountGoogle)
        .filter(AccountGoogle.google_user_id == google_user_id)
        .first()
    )
    if user is not None:
        return user

    if openid is not None:
        user = (
            db.session.query(Account)
            .join(AccountOpenID)
            .filter(AccountOpenID.openid == openid)
            .first()
        )
        if user is not None:
            db.session.query(AccountOpenID).filter(
                AccountOpenID.openid == openid
            ).delete()
            logger.info(
                "Migrated OpenID user %s to Google user %s", openid, google_user_id
            )

    if user is None:
        user = Account()
        user.name = "Google Account"
        user.apikey = generate_api_key()
        user.submission_count = 0
        db.session.add(user)
        db.session.flush()
        logger.info("Created user %s (%s)", user.id, user.name)

    google_user = AccountGoogle()
    google_user.account = user
    google_user.google_user_id = google_user_id
    db.session.add(google_user)
    logger.info(
        "Associated user %s (%s) with Google user %s",
        user.id,
        user.name,
        google_user_id,
    )

    return user


def handle_google_oauth2_login():
    google = OAuth2Service(
        name="google",
        client_id=current_app.config["GOOGLE_OAUTH_CLIENT_ID"],
        client_secret=current_app.config["GOOGLE_OAUTH_CLIENT_SECRET"],
        base_url="https://google.com",
        authorize_url="https://accounts.google.com/o/oauth2/auth",
        access_token_url="https://www.googleapis.com/oauth2/v3/token",
    )

    code = request.args.get("code")
    if not code:
        url = google.get_authorize_url(
            **{
                "response_type": "code",
                "access_type": "online",
                "scope": "openid email",
                "redirect_uri": url_for(".google_login", _external=True),
                "openid.realm": get_openid_realm(),
                "state": generate_login_token("google_login_token"),
            }
        )
        return redirect(url)

    # Before the code is spent: an authorization code we were not expecting is
    # someone else's, and exchanging it is the whole attack.
    check_login_token("google_login_token", request.args.get("state"))

    response = json.loads(
        google.get_raw_access_token(
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": url_for(".google_login", _external=True),
            }
        ).content
    )

    if "id_token" not in response:
        # Google returns {"error": "invalid_grant"} for an authorization code
        # that was already used or has expired -- typically someone reloading
        # the callback URL. Without this the KeyError hides what went wrong.
        # Log the error and the keys only -- a response without an id_token can
        # still carry an access_token, which must not reach the logs.
        raise LoginError(
            "Your Google sign-in link has expired. Please try again.",
            "Google token endpoint returned no id_token (error=%r, "
            "error_description=%r, keys=%r)"
            % (
                response.get("error"),
                response.get("error_description"),
                sorted(response),
            ),
        )

    # The signature is not checked. That is sound only because the token comes
    # straight from Google's token endpoint over TLS, in exchange for a code
    # redeemed with our client secret (OpenID Connect Core 3.1.3.7). It must
    # never be taken from the browser, as in the implicit flow.
    header, payload, secret = str(response["id_token"]).split(".")
    payload += "=" * (4 - (len(payload) % 4))
    id_token = json.loads(base64.urlsafe_b64decode(payload))

    user = find_or_create_google_user(id_token["sub"], id_token.get("openid_id"))
    logger.info('Google user %s "%s" logged in', user.id, user.name)
    store_google_email(user, id_token)

    return login_user_and_redirect(user.id)


GMAIL_DOMAINS = ("gmail.com", "googlemail.com")


def store_google_email(user: Account, id_token: dict[str, Any]) -> None:
    """Give the account the address from Google's ID token, if Google has
    verified it, Google hosts it, and the account has none yet.

    An address another account has already verified is left alone: accounts
    are never merged, and the unique index would refuse it anyway.
    """
    if user.email is not None:
        return
    # A JSON boolean, though older tokens had the string "true". Compared
    # exactly, so nothing else that happens to be truthy counts.
    verified = id_token.get("email_verified")
    if not (verified is True or verified == "true"):
        return
    email = normalize_email(str(id_token.get("email") or ""))
    if email is None:
        return
    # email_verified only says the address was verified once, when it was
    # added to the Google account, possibly years ago. Only for an address
    # Google itself hosts, Gmail or a Workspace domain (the hd claim), does
    # signing in with Google show the person still controls it. Anything else
    # could have passed to someone else since, who could then sign in by email.
    domain = email.rpartition("@")[2]
    if domain not in GMAIL_DOMAINS and not id_token.get("hd"):
        return
    if set_account_email(db.get_app_db(), user.id, email, only_if_unset=True):
        db.session.expire(user, ["email", "email_verified"])
        logger.info("Stored the email address from Google for user %s", user.id)


@user_page.route("/login/google")
def google_login():
    try:
        response = handle_google_oauth2_login()
        db.session.commit()
    except LoginError as e:
        logger.warning("Google login failed: %s", e)
        db.session.rollback()
        return redirect(url_for(".login", error=e.message))
    except Exception:
        logger.exception("Google login failed")
        db.session.rollback()
        return redirect(url_for(".login", error="Google authentication failed"))
    return response


@user_page.route("/logout")
def logout():
    if "id" in session:
        del session["id"]
    return redirect(url_for("general.index"))


# Where the CSRF token for the forms on the account page is kept in the
# session. The name predates the other forms.
ACCOUNT_CSRF_TOKEN_KEY = "api_key_csrf_token"

# What the account page says after a redirect. Kept in the session, so a link
# cannot make the page say something.
NOTICE_KEY = "account_notice"

NOTICES = {
    "sent": "We sent a confirmation link to {email}. It works for {minutes} minutes.",
    "confirmed": "Your email address is now {email}.",
}


def account_csrf_token() -> str:
    token = session.get(ACCOUNT_CSRF_TOKEN_KEY)
    if not token:
        token = session[ACCOUNT_CSRF_TOKEN_KEY] = secrets.token_urlsafe(32)
    return token


def check_account_csrf_token() -> None:
    token = session.get(ACCOUNT_CSRF_TOKEN_KEY)
    sent = request.form.get("csrf_token", "")
    if not token or not hmac.compare_digest(token, sent):
        abort(400)


def set_notice(name: str, email: str) -> None:
    session[NOTICE_KEY] = (name, mask_email(email))


def pop_notice() -> str | None:
    notice = session.pop(NOTICE_KEY, None)
    if not notice:
        return None
    name, email = notice
    minutes = int(CONFIRMATION_TTL.total_seconds() // 60)
    return NOTICES[name].format(email=email, minutes=minutes)


def render_account_page(
    user: Account,
    email_value: str = "",
    email_error: str | None = None,
    status: int = 200,
) -> Response:
    body = render_template(
        "apikey.html",
        title="Your account",
        user=user,
        apikey=user.apikey,
        masked_email=mask_email(user.email) if user.email else None,
        email_value=email_value,
        email_error=email_error,
        notice=pop_notice(),
        csrf_token=account_csrf_token(),
    )
    return make_response(body, status)


@user_page.route("/api-key")
def api_key():
    return render_account_page(require_user())


# POST only, and with the token from the account page, so another site can't
# replace someone's key, neither by linking to it nor by posting a form.
@user_page.route("/new-api-key", methods=["POST"])
def new_api_key():
    user = require_user()
    check_account_csrf_token()
    old_apikey = user.apikey
    user.apikey = generate_api_key()
    db.session.commit()
    for apikey in (old_apikey, user.apikey):
        refresh_cached_user_key(db.get_redis(), db.get_app_db(), apikey)
    return redirect(url_for(".api_key"))
