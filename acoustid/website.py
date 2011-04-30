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
from werkzeug.exceptions import NotFound, abort, HTTPException
from werkzeug.utils import cached_property
from werkzeug.contrib.securecookie import SecureCookie
from acoustid.handler import Handler, Response
from acoustid.data.application import (
    find_applications_by_account,
    insert_application,
)
from acoustid.data.account import (
    lookup_account_id_by_mbuser,
    lookup_account_id_by_openid,
    insert_account,
    get_account_details,
    reset_account_apikey,
)
from acoustid.data.stats import (
    find_current_stats,
    find_top_contributors,
    find_all_contributors,
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
    def create_from_server(cls, server, **args):
        self = cls(server.config.website, server.templates, server.engine.connect)
        self.url_args = args
        return self

    def handle(self, req):
        self.session = SecureCookie.load_cookie(req, secret_key=self.config.secret)
        try:
            resp = self._handle_request(req)
        except HTTPException, e:
            resp = e.get_response(req.environ)
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

    def require_user(self):
        if 'id' not in self.session:
            raise abort(redirect(self.login_url))


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
                    realm = self.config.base_https_url.rstrip('/')
                    url = openid_req.redirectURL(realm, self.login_url)
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
        self.require_user()
        title = 'Your API Key'
        info = get_account_details(self.conn, self.session['id'])
        return self.render_template('apikey.html', apikey=info['apikey'], title=title)


class NewAPIKeyHandler(WebSiteHandler):

    def _handle_request(self, req):
        self.require_user()
        reset_account_apikey(self.conn, self.session['id'])
        return redirect(self.config.base_url + 'api-key')


class ApplicationsHandler(WebSiteHandler):

    def _handle_request(self, req):
        self.require_user()
        title = 'Your Applications'
        applications = find_applications_by_account(self.conn, self.session['id'])
        return self.render_template('applications.html', title=title,
            applications=applications)


class NewApplicationHandler(WebSiteHandler):

    def _handle_request(self, req):
        self.require_user()
        errors = []
        title = 'New Applications'
        if req.form.get('submit'):
            name = req.form.get('name')
            version = req.form.get('version')
            if name and version:
                insert_application(self.conn, {
                    'name': name,
                    'version': version,
                    'account_id': self.session['id'],
                })
                return redirect(self.config.base_url + 'applications')
            else:
                if not name:
                    errors.append('Missing application name')
                if not version:
                    errors.append('Missing version number')
        return self.render_template('new-application.html', title=title,
            form=req.form, errors=errors)


def percent(x, total):
    if total == 0:
        x = 0
        total = 1
    return '%.2f' % (100.0 * x / total,)


class StatsHandler(WebSiteHandler):

    def _get_pie_chart(self, stats, pattern):
        track_mbid_data = []
        for i in range(11):
            track_mbid_data.append(stats.get(pattern % i, 0))
        track_mbid_sum = sum(track_mbid_data)
        track_mbid = []
        for i, count in enumerate(track_mbid_data):
            if i == 0:
                continue
            track_mbid.append({
                'i': i,
                'count': count,
                'percent': percent(count, track_mbid_sum),
            })
        return track_mbid

    def _handle_request(self, req):
        title = 'Statistics'
        stats = find_current_stats(self.conn)
        basic = {
            'submissions': stats.get('submission.all', 0),
            'fingerprints': stats.get('fingerprint.all', 0),
            'tracks': stats.get('track.all', 0),
            'mbids': stats.get('track_mbid.unique', 0),
            'contributors': stats.get('account.active', 0),
        }
        track_mbid = self._get_pie_chart(stats, 'track.%dmbids')
        mbid_track = self._get_pie_chart(stats, 'mbid.%dtracks')
        basic['tracks_with_mbid'] = basic['tracks'] - stats.get('track.0mbids', 0)
        basic['tracks_with_mbid_percent'] = percent(basic['tracks_with_mbid'], basic['tracks'])
        top_contributors = find_top_contributors(self.conn)
        return self.render_template('stats.html', title=title, basic=basic,
            track_mbid=track_mbid, mbid_track=mbid_track,
            top_contributors=top_contributors)


class ContributorsHandler(WebSiteHandler):

    def _handle_request(self, req):
        title = 'Contributors'
        contributors = find_all_contributors(self.conn)
        return self.render_template('contributors.html', title=title,
            contributors=contributors)


class TrackHandler(WebSiteHandler):

    def _handle_request(self, req):
        from acoustid.data.track import get_track_fingerprint_matrix, lookup_mbids
        from acoustid.data.musicbrainz import lookup_recording_metadata
        track_id = self.url_args['id']
        title = 'Track #%d' % (track_id,)
        matrix = get_track_fingerprint_matrix(self.conn, track_id)
        ids = sorted(matrix.keys())
        if not ids:
            return self.render_template('track-not-found.html', title=title,
                track_id=track_id)
        fingerprints = [{'id': id, 'i': i + 1} for i, id in enumerate(ids)]
        color1 = (172, 0, 0)
        color2 = (255, 255, 255)
        for id1 in ids:
            for id2 in ids:
                sim = matrix[id1][id2]
                color = [color1[i] + (color2[i] - color1[i]) * sim for i in range(3)]
                matrix[id1][id2] = {
                    'value': sim,
                    'color': '#%02x%02x%02x' % tuple(color),
                }
        mbids = lookup_mbids(self.conn, [track_id])[track_id]
        metadata = lookup_recording_metadata(self.conn, mbids)
        recordings = []
        for mbid in mbids:
            recording = metadata.get(mbid, {})
            recording['mbid'] = mbid
            recordings.append(recording)
        recordings.sort(key=lambda r: r.get('name', r.get('mbid')))
        return self.render_template('track.html', title=title,
            matrix=matrix, fingerprints=fingerprints, recordings=recordings)

