# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import os
import re
import json
import random
import logging
import urlparse
import urllib
import urllib2
#from wtforms import Form, BooleanField, TextField, validators
from openid import oidutil, fetchers
from openid.consumer import consumer as openid
from openid.extensions import ax, sreg
from sqlalchemy import sql
from sqlalchemy.orm import joinedload, load_only
from acoustid import tables as schema
from werkzeug import redirect
from werkzeug.exceptions import NotFound, abort, HTTPException, Forbidden
from werkzeug.utils import cached_property
from werkzeug.urls import url_encode, url_decode
from werkzeug.contrib.securecookie import SecureCookie
from acoustid.handler import Handler, Response
from acoustid.db import DatabaseContext
from acoustid.models import TrackMBIDChange, TrackMeta
from acoustid.data.track import resolve_track_gid
from acoustid.data.application import (
    find_applications_by_account,
    insert_application,
    update_application,
)
from acoustid.data.account import (
    lookup_account_id_by_mbuser,
    lookup_account_id_by_openid,
    insert_account,
    get_account_details,
    reset_account_apikey,
    update_account_lastlogin,
    is_moderator,
)
from acoustid.data.stats import (
    find_current_stats,
    find_daily_stats,
    find_top_contributors,
    find_all_contributors,
    find_lookup_stats,
    find_application_lookup_stats,
)

logger = logging.getLogger(__name__)


HTTP_TIMEOUT = 5

# monkey-patch uidutil.log to use the standard logging framework
openid_logger = logging.getLogger('openid')
def log_openid_messages(message, level=0):
    openid_logger.info(message)
oidutil.log = log_openid_messages

# force the use urllib2 with a timeout
fetcher = fetchers.Urllib2Fetcher()
fetcher.urlopen = lambda req: urllib2.urlopen(req, timeout=HTTP_TIMEOUT)
fetchers.setDefaultFetcher(fetcher)


class DigestAuthHandler(urllib2.HTTPDigestAuthHandler):
    """Patched DigestAuthHandler to correctly handle Digest Auth according to RFC 2617.

    This will allow multiple qop values in the WWW-Authenticate header (e.g. "auth,auth-int").
    The only supported qop value is still auth, though.
    See http://bugs.python.org/issue9714

    @author Kuno Woudt
    """
    def get_authorization(self, req, chal):
        qop = chal.get('qop')
        if qop and ',' in qop and 'auth' in qop.split(','):
            chal['qop'] = 'auth'
        return urllib2.HTTPDigestAuthHandler.get_authorization(self, req, chal)


class WebSiteHandler(Handler):

    def __init__(self, config, templates, connect=None):
        self.config = config
        self.templates = templates
        self.connect = connect

    @cached_property
    def conn(self):
        return self.connect()

    @cached_property
    def db(self):
        return DatabaseContext(self.conn)

    def get_url(self, path='', proto=None):
        from flask import current_app, request, render_template
        if proto is None:
            proto = 'https' if self.req.is_secure else 'http'
        if proto:
            proto += ':'
        return '%s//%s/%s' % (proto, request.host, path)

    @property
    def login_url(self):
        return self.get_url('login', proto='https')

    @classmethod
    def create_from_flask(cls):
        from flask import current_app, request, render_template
        from acoustid.web import db
        config = current_app.acoustid_config.website
        self = cls(config, None, db.session.connection)
        self.render_template = render_template
        return self

    def handle(self, req):
        from flask import session
        self.session = session
        self.req = req
        try:
            resp = self._handle_request(req)
        except HTTPException, e:
            resp = e.get_response(req.environ)
        self.session.save_cookie(resp)
        return resp

    def render_template(self, name, **params):
        context = {
            'base_url': self.get_url(proto=''),
            'base_https_url': self.get_url(proto='https'),
            'account_id': self.session.get('id'),
        }
        context.update(params)
        html = self.templates.get_template(name).render(**context)
        return Response(html, content_type='text/html; charset=UTF-8')

    def require_user(self, req):
        if 'id' not in self.session:
            raise abort(redirect(self.login_url + '?' + url_encode({'return_url': req.url})))


class PageHandler(WebSiteHandler):

    def _handle_request(self, req):
        from markdown import Markdown
        filename = os.path.normpath(
            os.path.join(self.config.pages_path, self.url_args['page'] + '.md'))
        if not filename.startswith(self.config.pages_path):
            logger.warn('Attempting to access page outside of the pages directory: %s', filename)
            raise NotFound()
        try:
            text = open(filename, 'r').read().decode('utf8')
        except IOError:
            logger.warn('Page does not exist: %s', filename)
            raise NotFound()
        md = Markdown(extensions=['meta'])
        html = md.convert(text)
        title = ' '.join(md.Meta.get('title', []))
        return self.render_template('page.html', content=html, title=title)


class IndexHandler(Handler):

    @classmethod
    def create_from_server(cls, server, page=None):
        return PageHandler.create_from_server(server, page='index')


class LoginHandler(WebSiteHandler):

    def _handle_openid_login(self, req, errors):
        openid_url = req.form.get('openid_identifier')
        if openid_url:
            try:
                consumer = openid.Consumer(self.session, None)
                openid_req = consumer.begin(openid_url)
            except openid.DiscoveryFailure:
                logger.exception('Error in OpenID discovery')
                errors.append('Error while trying to verify the OpenID')
            else:
                if openid_req is None:
                    errors.append('No OpenID services found for the given URL')
                else:
                    ax_req = ax.FetchRequest()
                    ax_req.add(ax.AttrInfo('http://schema.openid.net/contact/email',
                              alias='email'))
                    ax_req.add(ax.AttrInfo('http://axschema.org/namePerson/friendly',
                              alias='nickname'))
                    openid_req.addExtension(ax_req)
                    realm = self.get_url(proto='https').rstrip('/')
                    url = openid_req.redirectURL(realm, self.login_url + '?' + url_encode({'return_url': req.values.get('return_url')}))
                    return redirect(url)
        else:
            errors.append('Missing OpenID')

    def _handle_openid_login_response(self, req, errors):
        consumer = openid.Consumer(self.session, None)
        info = consumer.complete(req.args, self.login_url)
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
            account_id = lookup_account_id_by_openid(self.conn, openid_url)
            if not account_id:
                account_id, account_api_key = insert_account(self.conn, {
                    'name': 'OpenID User',
                    'openid': openid_url,
                })
            else:
                update_account_lastlogin(self.conn, account_id)
            logger.info("Successfuly identified OpenID user %s (%d) with email '%s' and nickname '%s'",
                openid_url, account_id, values.get('email', ''), values.get('name', ''))
            self.session['id'] = account_id
        elif info.status == openid.CANCEL:
            errors.append('OpenID verification has been canceled')
        else:
            errors.append('OpenID verification failed')

    def is_our_url(self, url):
        parsed = urlparse.urlparse(url)
        return parsed.netloc == self.config.host

    def _handle_request(self, req):
        return_url = req.values.get('return_url')
        errors = []
        if 'login' in req.form:
            if req.form['login'] == 'musicbrainz':
                resp = self._handle_musicbrainz_login(req, errors)
            elif req.form['login'] == 'openid':
                resp = self._handle_openid_login(req, errors)
            if resp is not None:
                return resp
        if 'openid.mode' in req.args:
            self._handle_openid_login_response(req, errors)
        elif 'code' in req.args and 'state' in req.args:
            return_url = self._handle_musicbrainz_login_response(req, errors)
        if 'id' in self.session:
            if not return_url or not self.is_our_url(return_url):
                return_url = self.get_url('api-key')
            return redirect(return_url)
        return self.render_template('login.html', errors=errors, return_url=return_url)
