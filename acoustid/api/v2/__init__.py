# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import re
import logging
import operator
from acoustid.handler import Handler, Response
from acoustid.data.track import lookup_mbids, lookup_puids, resolve_track_gid
from acoustid.data.musicbrainz import lookup_metadata
from acoustid.data.submission import insert_submission
from acoustid.data.fingerprint import lookup_fingerprint, decode_fingerprint, FingerprintSearcher
from acoustid.data.format import find_or_insert_format
from acoustid.data.application import lookup_application_id_by_apikey
from acoustid.data.account import lookup_account_id_by_apikey
from acoustid.data.source import find_or_insert_source
from acoustid.data.meta import insert_meta
from acoustid.data.foreignid import find_or_insert_foreignid
from werkzeug.exceptions import HTTPException, abort
from werkzeug.utils import cached_property
from acoustid.utils import is_uuid, is_foreignid, is_int
from acoustid.api import serialize_response, errors

logger = logging.getLogger(__name__)


DEFAULT_FORMAT = 'json'
FORMATS = set(['xml', 'json', 'jsonp'])


class APIHandlerParams(object):

    def _parse_client(self, values, conn):
        application_apikey = values.get('client')
        if not application_apikey:
            raise errors.MissingParameterError('client')
        self.application_id = lookup_application_id_by_apikey(conn, application_apikey)
        if not self.application_id:
            raise errors.InvalidAPIKeyError()

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

    @cached_property
    def conn(self):
        return self._connect()

    @classmethod
    def create_from_server(cls, server):
        handler = cls(connect=server.engine.connect)
        handler.index = server.index
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

    def handle(self, req):
        params = self.params_class()
        try:
            try:
                params.parse(req.values, self.conn)
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
        self.track_gid = values.get('trackid')
        if self.track_gid and not is_uuid(self.track_gid):
            raise errors.InvalidUUIDError('trackid')
        if not self.track_gid:
            self.duration = values.get('duration', type=int)
            if not self.duration:
                raise errors.MissingParameterError('duration')
            fingerprint_string = values.get('fingerprint')
            if not fingerprint_string:
                raise errors.MissingParameterError('fingerprint')
            self.fingerprint = decode_fingerprint(fingerprint_string)
            if not self.fingerprint:
                raise errors.InvalidFingerprintError()


class LookupHandler(APIHandler):

    params_class = LookupHandlerParams
    recordings_name = 'recordings'

    def inject_puids(self, meta, result_map):
        for track_id, puids in lookup_puids(self.conn, self.el_result.keys()).iteritems():
            self.el_result[track_id]['puids'] = puids

    def _inject_recording_ids_internal(self, add=True):
        el_recording = {}
        track_mbid_map = lookup_mbids(self.conn, self.el_result.keys())
        for track_id, mbids in track_mbid_map.iteritems():
            result = self.el_result[track_id]
            if add:
                result[self.recordings_name] = recordings = []
            for mbid in mbids:
                if add:
                    recording = {'id': mbid}
                    recordings.append(recording)
                    el_recording.setdefault(mbid, []).append(recording)
                else:
                    el_recording.setdefault(mbid, []).append(result)
        return el_recording

    def extract_recording(self, m, only_id=False):
        recording = {'id': m['recording_id']}
        if only_id:
            return recording
        recording['title'] = m['recording_title']
        if m['recording_duration']:
            recording['duration'] = m['recording_duration']
        if m['recording_artists']:
            recording['artists'] = m['recording_artists']
        return recording

    def extract_release(self, m, only_id=False):
        release = {'id': m['release_id']}
        if only_id:
            return release
        release['title'] = m['release_title']
        release['medium_count'] = m['release_medium_count']
        release['track_count'] = m['release_track_count']
        if m['release_country']:
            release['country'] = m['release_country']
        if m['release_artists']:
            release['artists'] = m['release_artists']
        date = {}
        if m['release_date_year']:
            date['year'] = m['release_date_year']
        if m['release_date_month']:
            date['month'] = m['release_date_month']
        if m['release_date_day']:
            date['day'] = m['release_date_day']
        if date:
            release['date'] = date
        return release

    def extract_release_group(self, m, only_id=False):
        release_group = {'id': m['release_group_id']}
        if only_id:
            return release_group
        release_group['title'] = m['release_group_title']
        if m['release_group_type']:
            release_group['type'] = m['release_group_type']
        if m['release_group_artists']:
            release_group['artists'] = m['release_group_artists']
        return release_group

    def group_releases_by_recording(self, metadata, only_ids=False):
        metadata = sorted(metadata, key=operator.itemgetter('recording_id', 'release_id'))
        last_recording_id = None
        last_release_id = None
        releases = []
        for item in metadata:
            recording_id = item['recording_id']
            if recording_id != last_recording_id:
                if releases:
                    yield last_recording_id, releases
                last_recording_id = recording_id
                last_release_id = None
            release_id = item['release_id']
            if release_id != last_release_id:
                releases.append(self.extract_release(item, only_id=only_ids))
                last_release_id = release_id
        if releases:
            yield last_recording_id, releases

    def group_releases_by_release_group(self, metadata, only_ids=False):
        metadata = sorted(metadata, key=operator.itemgetter('release_group_id', 'release_id'))
        last_release_group_id = None
        last_release_id = None
        releases = []
        for item in metadata:
            release_group_id = item['release_group_id']
            if release_group_id != last_release_group_id:
                if releases:
                    yield last_release_group_id, releases
                last_release_group_id = release_group_id
                last_release_id = None
            release_id = item['release_id']
            if release_id != last_release_id:
                releases.append(self.extract_release(item, only_id=only_ids))
                last_release_id = release_id
        if releases:
            yield last_release_group_id, releases

    def group_release_groups_by_recording(self, metadata, only_ids=False):
        metadata = sorted(metadata, key=operator.itemgetter('recording_id', 'release_group_id'))
        last_recording_id = None
        last_release_group_id = None
        release_groups = []
        for item in metadata:
            recording_id = item['recording_id']
            if recording_id != last_recording_id:
                if release_groups:
                    yield last_recording_id, release_groups
                last_recording_id = recording_id
                last_release_group_id = None
            release_group_id = item['release_group_id']
            if release_group_id != last_release_group_id:
                release_groups.append(self.extract_release_group(item, only_id=only_ids))
                last_release_group_id = release_group_id
        if release_groups:
            yield last_recording_id, release_groups

    def group_tracks_by_release(self, metadata, only_ids=False):
        metadata = sorted(metadata, key=operator.itemgetter('release_id', 'medium_position', 'track_position'))
        last_release_id = None
        last_medium_pos = None
        mediums = []
        for item in metadata:
            release_id = item['release_id']
            if release_id != last_release_id:
                if mediums:
                    yield last_release_id, mediums
                mediums = []
                last_release_id = release_id
                last_medium_pos = None
            medium_pos = item['medium_position']
            if medium_pos != last_medium_pos:
                medium = {'position': medium_pos, 'tracks': []}
                medium['track_count'] = item['medium_track_count']
                if item['medium_format']:
                    medium['format'] = item['medium_format']
                mediums.append(medium)
                last_medium_pos = medium_pos
            track = {
                'position': item['track_position'],
                'title': item['track_title'],
                'artists': item['track_artists'],
            }
            mediums[-1]['tracks'].append(track)
        if mediums:
            yield last_release_id, mediums

    def inject_releases_to_els(self, releases, els, el_release):
        for el in els:
            el['releases'] = []
            for release in releases:
                el['releases'].append(release)
                el_release.setdefault(release['id'], []).append(release)

    def inject_release_groups_to_els(self, release_groups, els, el_release_group):
        for el in els:
            el['releasegroups'] = []
            for release_group in release_groups:
                el['releasegroups'].append(release_group)
                el_release_group.setdefault(release_group['id'], []).append(release_group)

    def _inject_releases_internal(self, meta, metadata, els, group_func):
        el_release = {}
        for el_id, releases in group_func(metadata, 'releaseids' in meta):
            self.inject_releases_to_els(releases, els[el_id], el_release)
        if 'tracks' in meta:
            for release_id, mediums in self.group_tracks_by_release(metadata):
                for el in el_release[release_id]:
                    if 'compress' in meta:
                        for medium in mediums:
                            for track in medium['tracks']:
                                if 'artists' in track and track['artists'] == el.get('artists'):
                                    del track['artists']
                    el['mediums'] = mediums

    def _inject_release_groups_internal(self, meta, metadata, els, group_func):
        el_release_group = {}
        for el_id, release_groups in group_func(metadata, 'releasegroupids' in meta):
            self.inject_release_groups_to_els(release_groups, els[el_id], el_release_group)
        if 'releases' in meta or 'releaseids' in meta:
            self._inject_releases_internal(meta, metadata, el_release_group, self.group_releases_by_release_group)
            if 'compress' in meta:
                for release_groups in el_release_group.itervalues():
                    for release_group in release_groups:
                        for release in release_group.get('releases', []):
                            if 'artists' in release and release['artists'] == release_group.get('artists'):
                                del release['artists']
                            if 'title' in release and release['title'] == release_group.get('title'):
                                del release['title']

    def inject_recordings(self, meta):
        el_recording = self._inject_recording_ids_internal(True)
        load_releases = False
        load_release_groups = False
        if 'releaseids' in meta or 'releases' in meta:
            load_releases = True
        if 'releasegroupids' in meta or 'releasegroups' in meta:
            load_releases = True
            load_release_groups = True
        metadata = lookup_metadata(self.conn, el_recording.keys(), load_releases=load_releases, load_release_groups=load_release_groups)
        last_recording_id = None
        only_recording_ids = 'recordingids' in meta
        for item in metadata:
            if last_recording_id != item['recording_id']:
                recording = self.extract_recording(item, only_recording_ids)
                last_recording_id = recording['id']
                for el in el_recording[recording['id']]:
                    el.update(recording)
        if 'releasegroups' in meta or 'releasegroupids' in meta:
            self._inject_release_groups_internal(meta, metadata, el_recording, self.group_release_groups_by_recording)
            if 'compress' in meta:
                for recordings in el_recording.itervalues():
                    for recording in recordings:
                        for release_group in recording.get('releasegroups', []):
                            for release in release_group.get('releases', []):
                                for medium in release.get('mediums', []):
                                    for track in medium['tracks']:
                                        if 'title' in track and track['title'] == recording.get('title'):
                                            del track['title']
                        if 'artists' in release_group and release_group['artists'] == recording.get('artists'):
                            del release_group['artists']
        elif 'releases' in meta or 'releaseids' in meta:
            self._inject_releases_internal(meta, metadata, el_recording, self.group_releases_by_recording)
            if 'compress' in meta:
                for recordings in el_recording.itervalues():
                    for recording in recordings:
                        for release in recording.get('releases', []):
                            for medium in release.get('mediums', []):
                                for track in medium['tracks']:
                                    if 'title' in track and track['title'] == recording.get('title'):
                                        del track['title']
                            if 'artists' in release and release['artists'] == recording.get('artists'):
                                del release['artists']

    def inject_releases(self, meta):
        el_recording = self._inject_recording_ids_internal(False)
        metadata = lookup_metadata(self.conn, el_recording.keys(), load_releases=True)
        self._inject_releases_internal(meta, metadata, el_recording, self.group_releases_by_recording)

    def inject_release_groups(self, meta):
        el_recording = self._inject_recording_ids_internal(False)
        metadata = lookup_metadata(self.conn, el_recording.keys(), load_releases=True, load_release_groups=True)
        self._inject_release_groups_internal(meta, metadata, el_recording, self.group_release_groups_by_recording)

    def inject_m2(self, meta):
        el_recording = self._inject_recording_ids_internal(True)
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
        if 'puids' in meta:
            self.inject_puids(meta, result_map)

    def _handle_internal(self, params):
        import time
        t = time.time()
        response = {}
        response['results'] = results = []
        if getattr(params, 'track_gid', None):
            track_id = resolve_track_gid(self.conn, params.track_gid)
            matches = [(0, track_id, params.track_gid, 1.0)]
        else:
            searcher = FingerprintSearcher(self.conn, self.index)
            matches = searcher.search(params.fingerprint, params.duration)
        result_map = {}
        for fingerprint_id, track_id, track_gid, score in matches:
            if track_id in result_map:
                continue
            result_map[track_id] = result = {'id': track_gid, 'score': score}
            results.append(result)
        logger.info("Lookup from %s: %s", params.application_id, result_map.keys())
        if params.meta and result_map:
            self.inject_metadata(params.meta, result_map)
        logger.info("Lookup took %s", time.time() - t)
        return response


def iter_args_suffixes(args, prefix):
    prefix_dot = prefix + '.'
    results = []
    for name in args.iterkeys():
        if name == prefix:
            results.append(None)
        elif name.startswith(prefix_dot):
            prefix, suffix = name.split('.', 1)
            if suffix.isdigit():
                results.append(int(suffix))
    results.sort()
    return ['.%d' % i if i is not None else '' for i in results]


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
        p['fingerprint'] = decode_fingerprint(fingerprint_string)
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
        with self.conn.begin():
            source_id = find_or_insert_source(self.conn, params.application_id, params.account_id)
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
                    insert_submission(self.conn, values)
        return {}

