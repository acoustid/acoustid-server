# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

import logging
from acoustid.handler import Handler, Response
from acoustid.data.track import lookup_mbids
from acoustid.data.musicbrainz import lookup_metadata
from acoustid.data.submission import insert_submission
from acoustid.data.fingerprintdata import FingerprintData
from acoustid.data.format import find_or_insert_format
from acoustid.data.application import lookup_application_id_by_apikey
from acoustid.data.account import lookup_account_id_by_apikey
from acoustid.data.source import find_or_insert_source
from acoustid.utils import singular
from werkzeug.exceptions import HTTPException, abort
from werkzeug.utils import cached_property
import xml.etree.cElementTree as etree
import json
import chromaprint


logger = logging.getLogger(__name__)


DEFAULT_FORMAT = 'xml'
FORMATS = set(['xml', 'json'])
FINGERPRINT_VERSION = 1


ERROR_UNKNOWN_FORMAT = 1
ERROR_MISSING_PARAMETER = 2
ERROR_INVALID_FINGERPRINT = 3
ERROR_INVALID_APIKEY = 4
ERROR_INTERNAL = 5
ERROR_INVALID_USER_APIKEY = 6


def error(code, message, format=DEFAULT_FORMAT, status=400):
    response_data = {
        'status': 'error',
        'error': {
            'code': code,
            'message': message
        }
    }
    return serialize_response(response_data, format, status=status)


def ok(data, format=DEFAULT_FORMAT):
    response_data = {'status': 'ok'}
    response_data.update(data)
    return serialize_response(response_data, format)


def _serialize_xml_node(parent, data):
    if isinstance(data, dict):
        _serialize_xml_dict(parent, data)
    elif isinstance(data, list):
        _serialize_xml_list(parent, data)
    else:
        parent.text = unicode(data)


def _serialize_xml_dict(parent, data):
    for name, value in data.iteritems():
        elem = etree.SubElement(parent, name)
        _serialize_xml_node(elem, value)


def _serialize_xml_list(parent, data):
    name = singular(parent.tag)
    for item in data:
        elem = etree.SubElement(parent, name)
        _serialize_xml_node(elem, item)


def serialize_xml(data, **kwargs):
    root = etree.Element('response')
    _serialize_xml_node(root, data)
    res = etree.tostring(root, encoding="UTF-8")
    return Response(res, content_type='text/xml', **kwargs)


def serialize_json(data, **kwargs):
    res = json.dumps(data)
    return Response(res, content_type='text/json', **kwargs)


def serialize_response(data, format, **kwargs):
    if format == 'json':
        return serialize_json(data, **kwargs)
    else:
        return serialize_xml(data, **kwargs)


class BadRequest(HTTPException):

    code = 400

    def get_response(self, environ):
        return error_response(self.description)


class MissingArgument(BadRequest):

    def __init__(self, name):
        description = "Missing argument '%s'" % (name,)
        BadRequest.__init__(self, description)

class WebServiceError(Exception):

    def __init__(self, code, message):
        self.code = code
        self.message = message


class UnknownFormatError(WebServiceError):

    def __init__(self, name):
        message = 'unknown format "%s"' % (name,)
        WebServiceError.__init__(self, ERROR_UNKNOWN_FORMAT, message)


class MissingParameterError(WebServiceError):

    def __init__(self, name):
        message = 'missing required parameter "%s"' % (name,)
        WebServiceError.__init__(self, ERROR_MISSING_PARAMETER, message)
        self.parameter = name


class InvalidFingerprintError(WebServiceError):

    def __init__(self):
        message = 'invalid fingerprint'
        WebServiceError.__init__(self, ERROR_INVALID_FINGERPRINT, message)


class InvalidAPIKeyError(WebServiceError):

    def __init__(self):
        message = 'invalid API key'
        WebServiceError.__init__(self, ERROR_INVALID_APIKEY, message)


class InvalidUserAPIKeyError(WebServiceError):

    def __init__(self):
        message = 'invalid user API key'
        WebServiceError.__init__(self, ERROR_INVALID_USER_APIKEY, message)


class InternalError(WebServiceError):

    def __init__(self):
        message = 'internal error'
        WebServiceError.__init__(self, ERROR_INTERNAL, message)


class APIHandlerParams(object):

    def _parse_client(self, values, conn):
        application_apikey = values.get('client')
        if not application_apikey:
            raise MissingParameterError('client')
        self.application_id = lookup_application_id_by_apikey(conn, application_apikey)
        if not self.application_id:
            raise InvalidAPIKeyError()

    def parse(self, values, conn):
        self.format = values.get('format', DEFAULT_FORMAT)
        if self.format not in FORMATS:
            self.format = DEFAULT_FORMAT # used for the error response
            raise UnknownFormatError(self.format)


class APIHandler(Handler):

    params_class = None

    def handle(self, req):
        params = self.params_class()
        try:
            try:
                params.parse(req.values, self.conn)
                return ok(self._handle_internal(params), params.format)
            except WebServiceError:
                raise
            except StandardError:
                logger.exception('Error while handling API request')
                raise InternalError()
        except WebServiceError, e:
            return error(e.code, e.message, params.format)


class LookupHandlerParams(APIHandlerParams):

    def parse(self, values, conn):
        super(LookupHandlerParams, self).parse(values, conn)
        self._parse_client(values, conn)
        self.meta = values.get('meta', type=int)
        self.duration = values.get('duration', type=int)
        if not self.duration:
            raise MissingParameterError('duration')
        fingerprint_string = values.get('fingerprint')
        if not fingerprint_string:
            raise MissingParameterError('fingerprint')
        self.fingerprint, version = chromaprint.decode_fingerprint(fingerprint_string)
        if version != FINGERPRINT_VERSION:
            raise InvalidFingerprintError()


class LookupHandler(APIHandler):

    params_class = LookupHandlerParams

    def __init__(self, server=None, conn=None):
        self.server = server
        if conn is not None:
            self.__dict__['conn'] = conn
        self.fingerprint_data = FingerprintData(self.conn)

    @cached_property
    def conn(self):
        return self.server.engine.connect()

    def _inject_metadata(self, meta, result_map):
        track_mbid_map = lookup_mbids(self.conn, result_map.keys())
        if meta > 1:
            all_mbids = []
            for track_id, mbids in track_mbid_map.iteritems():
                all_mbids.extend(mbids)
            track_meta_map = lookup_metadata(self.conn, all_mbids)
        for track_id, mbids in track_mbid_map.iteritems():
            result = result_map[track_id]
            result['recordings'] = tracks = []
            for mbid in mbids:
                track = {}
                tracks.append(track)
                track['id'] = str(mbid)
                if meta == 1:
                    continue
                track_meta = track_meta_map.get(mbid)
                if track_meta is None:
                    continue
                track['name'] = track_meta['name']
                track['length'] = track_meta['length']
                track['artist'] = artist = {}
                artist['id'] = track_meta['artist_id']
                artist['name'] = track_meta['artist_name']
                track['releases'] = releases = []
                release = {}
                releases.append(release)
                release['id'] = track_meta['release_id']
                release['name'] = track_meta['release_name']
                release['track_num'] = track_meta['track_num']
                release['track_count'] = track_meta['total_tracks']

    def _handle_internal(self, params):
        response = {}
        response['results'] = results = []
        matches = self.fingerprint_data.search(params.fingerprint, params.duration, 0.7, 0.3)
        result_map = {}
        for fingerprint_id, track_id, score in matches:
            if track_id in result_map:
                continue
            result_map[track_id] = result = {'id': track_id, 'score': score}
            results.append(result)
        if params.meta and result_map:
            self._inject_metadata(params.meta, result_map)
        return response

    @classmethod
    def create_from_server(cls, server):
        return cls(server)


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
            raise MissingParameterError('user')
        self.account_id = lookup_account_id_by_apikey(conn, account_apikey)
        if not self.account_id:
            raise InvalidUserAPIKeyError()

    def _parse_submission(self, values, suffix):
        p = {}
        p['puid'] = values.get('puid' + suffix)
        p['mbids'] = values.getlist('mbid' + suffix)
        if not p['puid'] and not p['mbids']:
            raise MissingParameterError('mbid' + suffix)
        p['duration'] = values.get('duration' + suffix, type=int)
        fingerprint_string = values.get('fingerprint' + suffix)
        if not fingerprint_string:
            raise MissingParameterError('fingerprint' + suffix)
        p['fingerprint'], version = chromaprint.decode_fingerprint(fingerprint_string)
        if version != FINGERPRINT_VERSION:
            raise InvalidFingerprintError()
        p['bitrate'] = values.get('bitrate' + suffix, type=int)
        p['format'] = values.get('fileformat' + suffix)
        self.submissions.append(p)

    def parse(self, values, conn):
        super(SubmitHandlerParams, self).parse(values, conn)
        self._parse_client(values, conn)
        self._parse_user(values, conn)
        self.submissions = []
        for suffix in iter_args_suffixes(values, 'fingerprint'):
            self._parse_submission(values, suffix)
        if not self.submissions:
            raise MissingParameterError('fingerprint')


class SubmitHandler(Handler):

    def __init__(self, conn):
        self.conn = conn

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
                        'length': p['length'],
                        'format_id': format_ids[p['format']] if p['format'] else None,
                        'source_id': source_id
                    })
        return {}

    @classmethod
    def create_from_server(cls, server):
        conn = server.engine.connect()
        return cls(conn)

