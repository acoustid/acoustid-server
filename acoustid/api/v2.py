# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from acoustid.handler import Handler, Response
from acoustid.data.track import lookup_mbids
from acoustid.data.musicbrainz import lookup_metadata
from acoustid.data.submission import insert_submission
from acoustid.data.fingerprint import lookup_fingerprint, decode_fingerprint
from acoustid.data.format import find_or_insert_format
from acoustid.data.application import lookup_application_id_by_apikey
from acoustid.data.account import lookup_account_id_by_apikey
from acoustid.data.source import find_or_insert_source
from werkzeug.exceptions import HTTPException, abort
from werkzeug.utils import cached_property
from acoustid.utils import is_uuid
from acoustid.api import serialize_response, errors

logger = logging.getLogger(__name__)


DEFAULT_FORMAT = 'json'
FORMATS = set(['xml', 'json'])


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

    def parse(self, values, conn):
        self._parse_format(values)


class APIHandler(Handler):

    params_class = None

    def __init__(self, connect=None):
        self._connect = connect

    @cached_property
    def conn(self):
        return self._connect()

    @classmethod
    def create_from_server(cls, server):
        return cls(connect=server.engine.connect)

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
            return self._error(e.code, e.message, params.format, status=e.status)


class LookupHandlerParams(APIHandlerParams):

    def parse(self, values, conn):
        super(LookupHandlerParams, self).parse(values, conn)
        self._parse_client(values, conn)
        self.meta = values.get('meta', type=int)
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

    def _inject_metadata(self, meta, result_map):
        track_mbid_map = lookup_mbids(self.conn, result_map.keys())
        if meta > 1:
            all_mbids = []
            for track_id, mbids in track_mbid_map.iteritems():
                all_mbids.extend(mbids)
            track_meta_map = lookup_metadata(self.conn, all_mbids)
        for track_id, mbids in track_mbid_map.iteritems():
            result = result_map[track_id]
            result[self.recordings_name] = tracks = []
            for mbid in mbids:
                recording = {}
                tracks.append(recording)
                recording['id'] = str(mbid)
                if meta == 1:
                    continue
                track_meta = track_meta_map.get(mbid)
                if track_meta is None:
                    continue
                recording['tracks'] = [{
                    'title': track_meta['name'],
                    'duration': track_meta['length'],
                    'artist': {
                        'id': track_meta['artist_id'],
                        'name': track_meta['artist_name'],
                    },
                    'position': track_meta['track_num'],
                    'medium': {
                        'track_count': track_meta['total_tracks'],
                        # position
                        # title
                        # format
                        'release': {
                            'id': track_meta['release_id'],
                            'title': track_meta['release_name'],
                            # medium_count
                        },
                    },
                }]

    def _handle_internal(self, params):
        response = {}
        response['results'] = results = []
        matches = lookup_fingerprint(self.conn, params.fingerprint, params.duration, 0.7, 0.3)
        result_map = {}
        for fingerprint_id, track_id, score in matches:
            if track_id in result_map:
                continue
            result_map[track_id] = result = {'id': track_id, 'score': score}
            results.append(result)
        if params.meta and result_map:
            self._inject_metadata(params.meta, result_map)
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
        if not p['duration']:
            raise errors.MissingParameterError('duration' + suffix)
        p['format'] = values.get('fileformat' + suffix)

    def _parse_submission(self, values, suffix):
        p = {}
        p['puid'] = values.get('puid' + suffix)
        if p['puid'] and not is_uuid(p['puid']):
            raise errors.InvalidUUIDError('puid' + suffix)
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
        p['bitrate'] = values.get('bitrate' + suffix, type=int)
        self.submissions.append(p)

    def parse(self, values, conn):
        super(SubmitHandlerParams, self).parse(values, conn)
        self._parse_client(values, conn)
        self._parse_user(values, conn)
        self.submissions = []
        for suffix in iter_args_suffixes(values, 'fingerprint'):
            self._parse_submission(values, suffix)
        if not self.submissions:
            raise errors.MissingParameterError('fingerprint')


class SubmitHandler(APIHandler):

    params_class = SubmitHandlerParams

    def _handle_internal(self, params):
        with self.conn.begin():
            source_id = find_or_insert_source(self.conn, params.application_id, params.account_id)
            format_ids = {}
            for p in params.submissions:
                if p['format'] and p['format'] not in format_ids:
                    format_ids[p['format']] = find_or_insert_format(self.conn, p['format'])
            for p in params.submissions:
                for mbid in p['mbids']:
                    insert_submission(self.conn, {
                        'mbid': mbid or None,
                        'puid': p['puid'] or None,
                        'bitrate': p['bitrate'] or None,
                        'fingerprint': p['fingerprint'],
                        'length': p['duration'],
                        'format_id': format_ids[p['format']] if p['format'] else None,
                        'source_id': source_id
                    })
        return {}

