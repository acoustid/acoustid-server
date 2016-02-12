# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import re
import logging
import pprint
import json
import time
import operator
from acoustid import const
from acoustid.const import MAX_REQUESTS_PER_SECOND
from acoustid.handler import Handler, Response
from acoustid.data.track import lookup_mbids, resolve_track_gid, lookup_meta_ids
from acoustid.data.musicbrainz import lookup_metadata
from acoustid.data.submission import insert_submission, lookup_submission_status
from acoustid.data.fingerprint import lookup_fingerprint, decode_fingerprint, FingerprintSearcher
from acoustid.data.format import find_or_insert_format
from acoustid.data.application import lookup_application_id_by_apikey
from acoustid.data.account import lookup_account_id_by_apikey
from acoustid.data.source import find_or_insert_source
from acoustid.data.meta import insert_meta, lookup_meta
from acoustid.data.foreignid import find_or_insert_foreignid
from acoustid.data.stats import update_lookup_counter, update_user_agent_counter, update_lookup_avg_time
from acoustid.ratelimiter import RateLimiter
from werkzeug.exceptions import HTTPException, abort
from werkzeug.utils import cached_property
from acoustid.utils import is_uuid, is_foreignid, is_int, check_demo_client_api_key
from acoustid.api import serialize_response, errors

logger = logging.getLogger(__name__)


DEFAULT_FORMAT = 'json'
FORMATS = set(['xml', 'json', 'jsonp'])

DEMO_APPLICATION_ID = 2


def iter_args_suffixes(args, *prefixes):
    results = set()
    for name in args.iterkeys():
        for prefix in prefixes:
            if name == prefix:
                results.add(None)
            elif name.startswith(prefix + '.'):
                prefix, suffix = name.split('.', 1)
                if suffix.isdigit():
                    results.add(int(suffix))
    return ['.%d' % i if i is not None else '' for i in sorted(results)]


class APIHandlerParams(object):

    def __init__(self, config):
        self.config = config

    def _parse_client(self, values, conn):
        application_apikey = values.get('client')
        if not application_apikey:
            raise errors.MissingParameterError('client')
        self.application_id = lookup_application_id_by_apikey(conn, application_apikey)
        if not self.application_id:
            if check_demo_client_api_key(self.config.website.secret, application_apikey):
                self.application_id = DEMO_APPLICATION_ID
            else:
                logger.error("Invalid API key %s", application_apikey)
                raise errors.InvalidAPIKeyError()
        self.application_version = values.get('clientversion')

    def _parse_format(self, values):
        self.format = values.get('format', DEFAULT_FORMAT)
        if self.format not in FORMATS:
            self.format = DEFAULT_FORMAT # used for the error response
            raise errors.UnknownFormatError(self.format)
        if self.format == 'jsonp':
            callback = values.get('jsoncallback', 'jsonAcoustidApi')
            if not re.match('^[$A-Za-z_][0-9A-Za-z_]*(\.[$A-Za-z_][0-9A-Za-z_]*)*$', callback):
                callback = 'jsonAcoustidApi'
            self.format = '%s:%s' % (self.format, callback)

    def parse(self, values, conn):
        self._parse_format(values)


class APIHandler(Handler):

    params_class = None

    def __init__(self, connect=None):
        self._connect = connect
        self.index = None
        self.redis = None
        self.config = None
        self.cluster = None

    @cached_property
    def conn(self):
        return self._connect()

    @classmethod
    def create_from_server(cls, server):
        handler = cls(connect=server.engine.connect)
        handler.index = server.index
        handler.redis = server.redis
        handler.config = server.config
        handler.cluster = server.config.cluster
        return handler

    def _error(self, code, message, format=DEFAULT_FORMAT, status=400):
        response_data = {
            'status': 'error',
            'error': {
                'code': code,
                'message': message
            }
        }
        return serialize_response(response_data, format, status=status)

    def _ok(self, data, format=DEFAULT_FORMAT):
        response_data = {'status': 'ok'}
        response_data.update(data)
        return serialize_response(response_data, format)

    def _rate_limit(self, user_ip, application_id):
        ip_rate_limit = self.config.rate_limiter.ips.get(user_ip, MAX_REQUESTS_PER_SECOND)
        if self.rate_limiter.limit('ip', user_ip, ip_rate_limit):
            if application_id == DEMO_APPLICATION_ID:
                raise errors.TooManyRequests(ip_rate_limit)
        if application_id is not None:
            application_rate_limit = self.config.rate_limiter.applications.get(application_id)
            if application_rate_limit is not None:
                if self.rate_limiter.limit('app', application_id, application_rate_limit):
                    if application_id == DEMO_APPLICATION_ID:
                        raise errors.TooManyRequests(application_rate_limit)

    def handle(self, req):
        params = self.params_class(self.config)
        if req.access_route:
            self.user_ip = req.access_route[0]
        else:
            self.user_ip = req.remote_addr
        self.is_secure = req.is_secure
        self.user_agent = req.user_agent
        self.rate_limiter = RateLimiter(self.redis, 'rl')
        try:
            try:
                params.parse(req.values, self.conn)
                self._rate_limit(self.user_ip, getattr(params, 'application_id', None))
                return self._ok(self._handle_internal(params), params.format)
            except errors.WebServiceError:
                raise
            except StandardError:
                logger.exception('Error while handling API request')
                raise errors.InternalError()
        except errors.WebServiceError, e:
            logger.error("WS error: %s", e.message)
            return self._error(e.code, e.message, params.format, status=e.status)


class LookupHandlerParams(APIHandlerParams):

    duration_name = 'duration'

    def _parse_query(self, values, suffix):
        p = {}
        p['index'] = (suffix or '')[1:]
        p['track_gid'] = values.get('trackid' + suffix)
        if p['track_gid'] and not is_uuid(p['track_gid']):
            raise errors.InvalidUUIDError('trackid' + suffix)
        if not p['track_gid']:
            p['duration'] = values.get(self.duration_name + suffix, type=int)
            if not p['duration']:
                raise errors.MissingParameterError(self.duration_name + suffix)
            fingerprint_string = values.get('fingerprint' + suffix)
            if not fingerprint_string:
                raise errors.MissingParameterError('fingerprint' + suffix)
            p['fingerprint'] = decode_fingerprint(fingerprint_string.encode('ascii', 'ignore'))
            if not p['fingerprint']:
                raise errors.InvalidFingerprintError()
        self.fingerprints.append(p)

    def parse(self, values, conn):
        super(LookupHandlerParams, self).parse(values, conn)
        self._parse_client(values, conn)
        self.meta = values.get('meta')
        if self.meta == '0' or not self.meta:
            self.meta = []
        elif self.meta == '1':
            self.meta = ['recordingids']
        elif self.meta == '2':
            self.meta = ['m2']
        else:
            self.meta = self.meta.split()
        self.max_duration_diff = values.get('maxdurationdiff', type=int)
        if self.max_duration_diff is None:
            self.max_duration_diff = const.FINGERPRINT_MAX_LENGTH_DIFF
        elif self.max_duration_diff > const.FINGERPRINT_MAX_ALLOWED_LENGTH_DIFF or self.max_duration_diff < 1:
            raise errors.InvalidMaxDurationDiffError('maxdurationdiff')
        self.batch = values.get('batch', type=int)
        self.fingerprints = []
        suffixes = list(iter_args_suffixes(values, 'fingerprint', 'trackid'))
        if not suffixes:
            raise errors.MissingParameterError('fingerprint')
        for i, suffix in enumerate(suffixes):
            try:
                self._parse_query(values, suffix)
            except errors.WebServiceError:
                if not self.fingerprints and i + 1 == len(suffixes):
                    raise


class LookupHandler(APIHandler):

    params_class = LookupHandlerParams
    recordings_name = 'recordings'

    def _inject_recording_ids_internal(self, add=True, add_sources=False):
        el_recording = {}
        res_map = {}
        track_mbid_map = lookup_mbids(self.conn, self.el_result.keys())
        for track_id, mbids in track_mbid_map.iteritems():
            res_map[track_id] = []
            for mbid, sources in mbids:
                res_map[track_id].append(mbid)
                if add:
                    for result_el in self.el_result[track_id]:
                        recording = {'id': mbid}
                        if add_sources:
                            recording['sources'] = sources
                        result_el.setdefault(self.recordings_name, []).append(recording)
                        el_recording.setdefault(mbid, []).append(recording)
                else:
                    el_recording.setdefault(mbid, []).extend(self.el_result[track_id])
        return el_recording, res_map

    def _inject_user_meta_ids_internal(self, add=True):
        el_recording = {}
        track_meta_map = lookup_meta_ids(self.conn, self.el_result.keys())
        for track_id, meta_ids in track_meta_map.iteritems():
            for meta_id in meta_ids:
                if add:
                    for result_el in self.el_result[track_id]:
                        recording = {}
                        result_el.setdefault(self.recordings_name, []).append(recording)
                        el_recording.setdefault(meta_id, []).append(recording)
                else:
                    el_recording.setdefault(meta_id, []).extend(self.el_result[track_id])
        return el_recording, track_meta_map

    def extract_recording(self, m, only_id=False):
        recording = {'id': m['recording_id']}
        if only_id:
            return recording
        recording['title'] = m['recording_title'] or ''
        if m['recording_duration']:
            recording['duration'] = m['recording_duration']
        if m['recording_artists']:
            recording['artists'] = m['recording_artists']
        return recording

    def extract_release(self, m, only_id=False):
        release = {'id': m['release_id']}
        if only_id:
            return release
        release['title'] = m['release_title'] or ''
        if m['release_medium_count']:
            release['medium_count'] = m['release_medium_count']
        if m['release_track_count']:
            release['track_count'] = m['release_track_count']
        if m['release_artists']:
            release['artists'] = m['release_artists']
        if m['release_events']:
            release['releaseevents'] = []
            for rem in m['release_events']:
                release_event = {}
                if rem['release_country']:
                    release_event['country'] = rem['release_country']
                date = {}
                if rem['release_date_year']:
                    date['year'] = rem['release_date_year']
                if rem['release_date_month']:
                    date['month'] = rem['release_date_month']
                if rem['release_date_day']:
                    date['day'] = rem['release_date_day']
                if date:
                    release_event['date'] = date
                release['releaseevents'].append(release_event)
            release.update(release['releaseevents'][0])
        return release

    def extract_release_group(self, m, only_id=False):
        release_group = {'id': m['release_group_id']}
        if only_id:
            return release_group
        release_group['title'] = m['release_group_title'] or ''
        if m['release_group_primary_type']:
            release_group['type'] = m['release_group_primary_type']
        if m['release_group_secondary_types']:
            release_group['secondarytypes'] = m['release_group_secondary_types']
        if m['release_group_artists']:
            release_group['artists'] = m['release_group_artists']
        return release_group

    def _inject_release_groups_internal(self, meta, parent, metadata):
        release_groups = self._group_release_groups(metadata, 'releasegroupids' in meta)
        parent['releasegroups'] = []
        for release_group, release_group_metadata in release_groups:
            parent['releasegroups'].append(release_group)
            if 'releases' in meta or 'releaseids' in meta:
                self._inject_releases_internal(meta, release_group, release_group_metadata)
                if 'compress' in meta:
                    for release in release_group['releases']:
                        if 'artists' in release and release['artists'] == release_group.get('artists'):
                            del release['artists']
                        if 'title' in release and release['title'] == release_group.get('title'):
                            del release['title']

    def _inject_releases_internal(self, meta, parent, metadata):
        releases = self._group_releases(metadata, 'releaseids' in meta)
        parent['releases'] = []
        for release, release_metadata in releases:
            parent['releases'].append(release)
            if 'tracks' in meta:
                release['mediums'] = list(self._group_tracks(release_metadata))
                if 'compress' in meta:
                    for medium in release['mediums']:
                        for track in medium['tracks']:
                            if 'artists' in track and track['artists'] == release.get('artists'):
                                del track['artists']

    def inject_recordings(self, meta):
        recording_els = self._inject_recording_ids_internal(True, 'sources' in meta)[0]
        load_releases = False
        load_release_groups = False
        if 'releaseids' in meta or 'releases' in meta:
            load_releases = True
        if 'releasegroupids' in meta or 'releasegroups' in meta:
            load_releases = True
            load_release_groups = True
        metadata = lookup_metadata(self.conn, recording_els.keys(), load_releases=load_releases, load_release_groups=load_release_groups)
        if 'usermeta' in meta and not metadata:
            user_meta_els = self._inject_user_meta_ids_internal(True)[0]
            recording_els.update(user_meta_els)
            user_meta = lookup_meta(self.conn, user_meta_els.keys())
            metadata.extend(user_meta)
        for recording, recording_metadata in self._group_recordings(metadata, 'recordingids' in meta):
            if 'releasegroups' in meta or 'releasegroupids' in meta:
                self._inject_release_groups_internal(meta, recording, recording_metadata)
                if 'compress' in meta:
                    for release_group in recording.get('releasegroups', []):
                        for release in release_group.get('releases', []):
                            for medium in release.get('mediums', []):
                                for track in medium['tracks']:
                                    if 'title' in track and track['title'] == recording.get('title'):
                                        del track['title']
                    if 'artists' in release_group and release_group['artists'] == recording.get('artists'):
                        del release_group['artists']
            elif 'releases' in meta or 'releaseids' in meta:
                self._inject_releases_internal(meta, recording, recording_metadata)
                if 'compress' in meta:
                    for release in recording.get('releases', []):
                        for medium in release.get('mediums', []):
                            for track in medium['tracks']:
                                if 'title' in track and track['title'] == recording.get('title'):
                                    del track['title']
                        if 'artists' in release and release['artists'] == recording.get('artists'):
                            del release['artists']
            for recording_el in recording_els[recording['id']]:
                if 'usermeta' in meta:
                    if isinstance(recording['id'], int):
                        del recording['id']
                        if 'title' in recording and not recording['title']:
                            del recording['title']
                        if 'releasegroups' in recording:
                            releasegroups = []
                            for releasegroup in recording['releasegroups']:
                                del releasegroup['id']
                                if 'title' in releasegroup and not releasegroup['title']:
                                    del releasegroup['title']
                                if 'releases' in releasegroup:
                                    releases = []
                                    for release in releasegroup['releases']:
                                        del release['id']
                                        if 'title' in release and not release['title']:
                                            del release['title']
                                        if release:
                                            releases.append(release)
                                    if releases:
                                        releasegroup['releases'] = releases
                                    else:
                                        del releasegroup['releases']
                                if releasegroup:
                                    releasegroups.append(releasegroup)
                            if releasegroups:
                                recording['releasegroups'] = releasegroups
                            else:
                                del recording['releasegroups']
                        if 'releases' in recording:
                            releases = []
                            for release in recording['releases']:
                                del release['id']
                                if 'title' in release and not release['title']:
                                    del release['title']
                                if release:
                                    releases.append(release)
                            if releases:
                                recording['releases'] = releases
                            else:
                                del recording['releases']
                recording_el.update(recording)

    def inject_releases(self, meta):
        recording_els, track_mbid_map = self._inject_recording_ids_internal(False)
        metadata = lookup_metadata(self.conn, recording_els.keys(), load_releases=True, load_release_groups=True)
        for track_id, track_metadata in self._group_metadata(metadata, track_mbid_map):
            result = {}
            self._inject_releases_internal(meta, result, track_metadata)
            for result_el in self.el_result[track_id]:
                result_el.update(result)

    def inject_release_groups(self, meta):
        recording_els, track_mbid_map = self._inject_recording_ids_internal(False)
        metadata = lookup_metadata(self.conn, recording_els.keys(), load_releases=True, load_release_groups=True)
        for track_id, track_metadata in self._group_metadata(metadata, track_mbid_map):
            result = {}
            self._inject_release_groups_internal(meta, result, track_metadata)
            for result_el in self.el_result[track_id]:
                result_el.update(result)

    def _group_metadata(self, metadata, track_mbid_map):
        results = {}
        for track_id, mbids in track_mbid_map.iteritems():
            mbids = set(mbids)
            results[track_id] = []
            for item in metadata:
                if item['recording_id'] in mbids:
                    results[track_id].append(item)
        return results.iteritems()

    def _group_release_groups(self, metadata, only_ids=False):
        results = {}
        for item in metadata:
            id = item['release_group_id']
            if id not in results:
                results[id] = (self.extract_release_group(item, only_id=only_ids), [])
            results[id][1].append(item)
        return results.itervalues()

    def _group_recordings(self, metadata, only_ids=False):
        results = {}
        for item in metadata:
            id = item['recording_id']
            if id not in results:
                results[id] = (self.extract_recording(item, only_id=only_ids), [])
            results[id][1].append(item)
        return results.itervalues()

    def _group_releases(self, metadata, only_ids=False):
        results = {}
        for item in metadata:
            id = item['release_id']
            if id not in results:
                results[id] = (self.extract_release(item, only_id=only_ids), [])
            results[id][1].append(item)
        return results.itervalues()

    def _group_tracks(self, metadata):
        results = {}
        for item in metadata:
            medium_pos = item['medium_position']
            medium = results.get(medium_pos)
            if medium is None:
                medium = {'position': medium_pos, 'tracks': []}
                medium['track_count'] = item['medium_track_count']
                if item['medium_format']:
                    medium['format'] = item['medium_format']
                if item['medium_title']:
                    medium['title'] = item['medium_title']
                results[medium_pos] = medium
            track = {
                'id': item['track_id'],
                'position': item['track_position'],
                'title': item['track_title'],
                'artists': item['track_artists'],
            }
            medium['tracks'].append(track)
        return results.itervalues()

    def inject_m2(self, meta):
        el_recording = self._inject_recording_ids_internal(True)[0]
        metadata = lookup_metadata(self.conn, el_recording.keys(), load_releases=True)
        last_recording_id = None
        for item in metadata:
            if last_recording_id != item['recording_id']:
                recording = self.extract_recording(item, True)
                last_recording_id = recording['id']
                for el in el_recording[recording['id']]:
                    if item['recording_duration']:
                        recording['duration'] = item['recording_duration']
                    recording['tracks'] = []
                    el.update(recording)
        metadata = sorted(metadata, key=operator.itemgetter('recording_id', 'release_id', 'medium_position', 'track_position'))
        for item in metadata:
            for el in el_recording[item['recording_id']]:
                medium = {
                    'track_count': item['medium_track_count'],
                    'position': item['medium_position'],
                    'release': {
                        'id': item['release_id'],
                        'title': item['release_title'],
                    },
                }
                if item['medium_format']:
                    medium['format'] = item['medium_format']
                el['tracks'].append({
                    'title': item['track_title'],
                    'duration': item['track_duration'],
                    'artists': item['track_artists'],
                    'position': item['track_position'],
                    'medium': medium,
                })

    def inject_metadata(self, meta, result_map):
        self.el_result = result_map
        if 'm2' in meta:
            self.inject_m2(meta)
        elif 'recordings' in meta or 'recordingids' in meta:
            self.inject_recordings(meta)
        elif 'releasegroups' in meta or 'releasegroupids' in meta:
            self.inject_release_groups(meta)
        elif 'releases' in meta or 'releaseids' in meta:
            self.inject_releases(meta)

    def _inject_results(self, results, result_map, matches):
        seen = set()
        for fingerprint_id, track_id, track_gid, score in matches:
            if track_id in seen:
                continue
            seen.add(track_id)
            result = {'id': track_gid, 'score': score}
            result_map.setdefault(track_id, []).append(result)
            results.append(result)
        return seen

    def _handle_internal(self, params):
        import time
        t = time.time()
        update_user_agent_counter(self.redis, params.application_id, self.user_agent, self.user_ip)
        searcher = FingerprintSearcher(self.conn, self.index)
        searcher.max_length_diff = params.max_duration_diff
        if params.batch:
            fingerprints = params.fingerprints
        else:
            fingerprints = params.fingerprints[:1]
        all_matches = []
        for p in fingerprints:
            if p['track_gid']:
                track_id = resolve_track_gid(self.conn, p['track_gid'])
                matches = [(0, track_id, p['track_gid'], 1.0)]
            else:
                matches = searcher.search(p['fingerprint'], p['duration'])
            all_matches.append(matches)
        response = {}
        if params.batch:
            response['fingerprints'] = fps = []
            result_map = {}
            for p, matches in zip(fingerprints, all_matches):
                results = []
                fps.append({'index': p['index'], 'results': results})
                track_ids = self._inject_results(results, result_map, matches)
                update_lookup_counter(self.redis, params.application_id, bool(track_ids))
                logger.debug("Lookup from %s: %s", params.application_id, list(track_ids))
        else:
            response['results'] = results = []
            result_map = {}
            self._inject_results(results, result_map, all_matches[0])
            update_lookup_counter(self.redis, params.application_id, bool(result_map))
            logger.debug("Lookup from %s: %s", params.application_id, result_map.keys())
        if params.meta and result_map:
            self.inject_metadata(params.meta, result_map)
        if fingerprints:
            time_per_fp = (time.time() - t) / len(fingerprints)
            update_lookup_avg_time(self.redis, time_per_fp)
        return response


class SubmissionStatusHandlerParams(APIHandlerParams):

    def parse(self, values, conn):
        super(SubmissionStatusHandlerParams, self).parse(values, conn)
        self._parse_client(values, conn)
        self.ids = values.getlist('id', type=int)


class SubmissionStatusHandler(APIHandler):

    params_class = SubmissionStatusHandlerParams

    def _handle_internal(self, params):
        response = {'submissions': [{'id': id, 'status': 'pending'} for id in params.ids]}
        tracks = lookup_submission_status(self.conn, params.ids)
        for submission in response['submissions']:
            id = submission['id']
            track_gid = tracks.get(id)
            if track_gid is not None:
                submission['status'] = 'imported'
                submission['result'] = {'id': track_gid}
        return response


class SubmitHandlerParams(APIHandlerParams):

    def _parse_user(self, values, conn):
        account_apikey = values.get('user')
        if not account_apikey:
            raise errors.MissingParameterError('user')
        self.account_id = lookup_account_id_by_apikey(conn, account_apikey)
        if not self.account_id:
            raise errors.InvalidUserAPIKeyError()

    def _parse_duration_and_format(self, p, values, suffix):
        p['duration'] = values.get('duration' + suffix, type=int)
        if p['duration'] is None:
            raise errors.MissingParameterError('duration' + suffix)
        if p['duration'] <= 0 or p['duration'] > 0x7fff:
            raise errors.InvalidDurationError('duration' + suffix)
        p['format'] = values.get('fileformat' + suffix)

    def _parse_submission(self, values, suffix):
        p = {}
        p['index'] = (suffix or '')[1:]
        p['puid'] = values.get('puid' + suffix)
        if p['puid'] and not is_uuid(p['puid']):
            raise errors.InvalidUUIDError('puid' + suffix)
        p['foreignid'] = values.get('foreignid' + suffix)
        if p['foreignid'] and not is_foreignid(p['foreignid']):
            raise errors.InvalidForeignIDError('foreignid' + suffix)
        p['mbids'] = values.getlist('mbid' + suffix)
        if p['mbids'] and not all(map(is_uuid, p['mbids'])):
            raise errors.InvalidUUIDError('mbid' + suffix)
        self._parse_duration_and_format(p, values, suffix)
        fingerprint_string = values.get('fingerprint' + suffix)
        if not fingerprint_string:
            raise errors.MissingParameterError('fingerprint' + suffix)
        p['fingerprint'] = decode_fingerprint(fingerprint_string.encode('ascii', 'ignore'))
        if not p['fingerprint']:
            raise errors.InvalidFingerprintError()
        p['bitrate'] = values.get('bitrate' + suffix, type=int) or None
        if p['bitrate'] is not None and p['bitrate'] <= 0:
            raise errors.InvalidBitrateError('bitrate' + suffix)
        p['track'] = values.get('track' + suffix)
        p['artist'] = values.get('artist' + suffix)
        p['album'] = values.get('album' + suffix)
        p['album_artist'] = values.get('albumartist' + suffix)
        p['track_no'] = values.get('trackno' + suffix, type=int)
        p['disc_no'] = values.get('discno' + suffix, type=int)
        p['year'] = values.get('year' + suffix, type=int)
        self.submissions.append(p)

    def parse(self, values, conn):
        super(SubmitHandlerParams, self).parse(values, conn)
        self._parse_client(values, conn)
        self._parse_user(values, conn)
        self.wait = values.get('wait', type=int, default=0)
        self.submissions = []
        suffixes = list(iter_args_suffixes(values, 'fingerprint'))
        if not suffixes:
            raise errors.MissingParameterError('fingerprint')
        for i, suffix in enumerate(suffixes):
            try:
                self._parse_submission(values, suffix)
            except errors.WebServiceError:
                if not self.submissions and i + 1 == len(suffixes):
                    raise


class SubmitHandler(APIHandler):

    params_class = SubmitHandlerParams
    meta_fields = ('track', 'artist', 'album', 'album_artist', 'track_no',
                   'disc_no', 'year')

    def _handle_internal(self, params):
        response = {'submissions': []}
        ids = set()
        with self.conn.begin():
            source_id = find_or_insert_source(self.conn, params.application_id, params.account_id, params.application_version)
            format_ids = {}
            for p in params.submissions:
                if p['format']:
                    if p['format'] not in format_ids:
                        format_ids[p['format']] = find_or_insert_format(self.conn, p['format'])
                    p['format_id'] = format_ids[p['format']]
            for p in params.submissions:
                mbids = p['mbids'] or [None]
                for mbid in mbids:
                    values = {
                        'mbid': mbid or None,
                        'puid': p['puid'] or None,
                        'bitrate': p['bitrate'] or None,
                        'fingerprint': p['fingerprint'],
                        'length': p['duration'],
                        'format_id': p.get('format_id'),
                        'source_id': source_id
                    }
                    meta_values = dict((n, p[n] or None) for n in self.meta_fields)
                    if any(meta_values.itervalues()):
                        values['meta_id'] = insert_meta(self.conn, meta_values)
                    if p['foreignid']:
                        values['foreignid_id'] = find_or_insert_foreignid(self.conn, p['foreignid'])
                    id = insert_submission(self.conn, values)
                    ids.add(id)
                    submission = {'id': id, 'status': 'pending'}
                    if p['index']:
                        submission['index'] = p['index']
                    response['submissions'].append(submission)

        if self.redis is not None:
            self.redis.publish('channel.submissions', json.dumps(list(ids)))

        clients_waiting_key = 'submission.waiting'
        clients_waiting = self.redis.incr(clients_waiting_key) - 1
        try:
            max_wait = 10
            self.redis.expire(clients_waiting_key, max_wait)
            tracks = {}
            remaining = min(max(0, max_wait - 2 ** clients_waiting), params.wait)
            logger.debug('starting to wait at %f %d', remaining, clients_waiting)
            while remaining > 0 and ids:
                logger.debug('waiting %f seconds', remaining)
                time.sleep(0.5) # XXX replace with LISTEN/NOTIFY
                remaining -= 0.5
                tracks = lookup_submission_status(self.conn, ids)
                if not tracks:
                    continue
                for submission in response['submissions']:
                    id = submission['id']
                    track_gid = tracks.get(id)
                    if track_gid is not None:
                        submission['status'] = 'imported'
                        submission['result'] = {'id': track_gid}
                        ids.remove(id)
        finally:
            self.redis.decr(clients_waiting_key)

        return response

