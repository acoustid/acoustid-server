# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import os
import logging
import urllib
import urllib2
from openid import oidutil, fetchers
from openid.consumer import consumer as openid
from openid.extensions import ax, sreg
from werkzeug import redirect
from werkzeug.exceptions import NotFound
from werkzeug.utils import cached_property
from werkzeug.contrib.securecookie import SecureCookie
from acoustid.handler import Handler, Response
from acoustid.data.account import (
    lookup_account_id_by_mbuser,
    lookup_account_id_by_openid,
    insert_account,
    get_account_details,
    reset_account_apikey,
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


class WebSiteHandler(Handler):

    def __init__(self, config, templates, connect=None):
        self.config = config
        self.templates = templates
        self.connect = connect

    @cached_property
    def conn(self):
        return self.connect()

    @property
    def login_url(self):
        return self.config.base_https_url + 'login'

    @classmethod
    def create_from_server(cls, server):
        return cls(server.config.website, server.templates, server.engine.connect)

    def handle(self, req):
        self.session = SecureCookie.load_cookie(req, secret_key=self.config.secret)
        resp = self._handle_request(req)
        self.session.save_cookie(resp)
        return resp

    def render_template(self, name, **params):
        context = {
            'base_url': self.config.base_url,
            'base_https_url': self.config.base_https_url or self.config.base_url,
            'account_id': self.session.get('id'),
        }
        context.update(params)
        html = self.templates.get_template(name).render(**context)
        return Response(html, content_type='text/html; charset=UTF-8')


class PageHandler(WebSiteHandler):

    @classmethod
    def create_from_server(cls, server, page=None):
        self = cls(server.config.website, server.templates, server.engine.connect)
        self.filename  = os.path.normpath(
            os.path.join(server.config.website.pages_path, page + '.md'))
        return self

    def _handle_request(self, req):
        from markdown import Markdown
        if not self.filename.startswith(self.config.pages_path):
            logger.warn('Attempting to access page outside of the pages directory: %s', self.filename)
            raise NotFound()
        try:
            text = open(self.filename, 'r').read().decode('utf8')
        except IOError:
            logger.warn('Page does not exist: %s', self.filename)
            raise NotFound()
        md = Markdown(extensions=['meta'])
        html = md.convert(text)
        title = ' '.join(md.Meta.get('title', []))
        return self.render_template('page.html', content=html, title=title)


class IndexHandler(Handler):

    @classmethod
    def create_from_server(cls, server, page=None):
        return PageHandler.create_from_server(server, 'index')


def check_mb_account(username, password):
    data = {'type': 'xml', 'name': username}
    url = 'http://musicbrainz.org/ws/1/user?' + urllib.urlencode(data)
    auth_handler = urllib2.HTTPDigestAuthHandler()
    auth_handler.add_password('musicbrainz.org', 'http://musicbrainz.org/',
                              username, password)
    opener = urllib2.build_opener(auth_handler)
    try:
        opener.open(url, timeout=HTTP_TIMEOUT)
    except StandardError:
        return False
    return True


class LoginHandler(WebSiteHandler):

    def _handle_musicbrainz_login(self, req, errors):
        username = req.form.get('mb_user')
        password = req.form.get('mb_password')
        if username and password:
            if check_mb_account(username, password):
                account_id = lookup_account_id_by_mbuser(self.conn, username)
                if not account_id:
                    account_id = insert_account(self.conn, {
                        'name': username,
                        'mbuser': username,
                    })
                logger.info("Successfuly identified MusicBrainz user %s (%d)", username, account_id)
                self.session['id'] = account_id
            else:
                errors.append('Invalid username or password')
        else:
            if not username:
                errors.append('Missing username')
            if not password:
                errors.append('Missing password')

    def _handle_openid_login(self, req, errors):
        openid_url = req.form.get('openid_identifier')
        if openid_url:
            try:
                consumer = openid.Consumer(self.session, None)
                openid_req = consumer.begin(openid_url)
            except openid.DiscoveryFailure:
                logger.traceback('Error in OpenID discovery')
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
                    url = openid_req.redirectURL(self.config.base_url, self.login_url)
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
                account_id = insert_account(self.conn, {
                    'name': 'OpenID User',
                    'openid': openid_url,
                })
            logger.info("Successfuly identified OpenID user %s (%d) with email '%s' and nickname '%s'",
                openid_url, account_id, values.get('email', ''), values.get('name', ''))
            self.session['id'] = account_id
        elif info.status == openid.CANCEL:
            errors.append('OpenID verification has been canceled')
        else:
            errors.append('OpenID verification failed')

    def _handle_request(self, req):
        errors = {'openid': [], 'mb': []}
        if 'login' in req.form:
            if req.form['login'] == 'mb':
                self._handle_musicbrainz_login(req, errors['mb'])
            elif req.form['login'] == 'openid':
                resp = self._handle_openid_login(req, errors['openid'])
                if resp is not None:
                    return resp
        if 'openid.mode' in req.args:
            self._handle_openid_login_response(req, errors['openid'])
        if 'id' in self.session:
            return redirect(self.config.base_url + 'api-key')
        return self.render_template('login.html', errors=errors)


class LogoutHandler(WebSiteHandler):

    def _handle_request(self, req):
        if 'id' in self.session:
            del self.session['id']
        return redirect(self.config.base_url)


class APIKeyHandler(WebSiteHandler):

    def _handle_request(self, req):
        if 'id' not in self.session:
            return redirect(self.login_url)
        title = 'Your API Key'
        info = get_account_details(self.conn, self.session['id'])
        return self.render_template('apikey.html', apikey=info['apikey'], title=title)


class NewAPIKeyHandler(WebSiteHandler):

    def _handle_request(self, req):
        if 'id' not in self.session:
            return redirect(self.login_url)
        reset_account_apikey(self.conn, self.session['id'])
        return redirect(self.config.base_url + 'api-key')

