# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details. 

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
from werkzeug.exceptions import HTTPException
import xml.etree.cElementTree as etree
import json
import chromaprint


def error_response(error):
    data = {
        'status': 'error',
        'error': {
            'code': 1,
            'message': error
        }
    }
    return serialize_response(data)


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


def serialize_xml(data):
    root = etree.Element('response')
    _serialize_xml_node(root, data)
    res = etree.tostring(root, encoding="UTF-8")
    return Response(res, content_type='text/xml')


def serialize_json(data):
    res = json.dumps(data)
    return Response(res, content_type='text/json')


def serialize_response(data, format):
    if format == 'json':
        return serialize_json(data)
    else:
        return serialize_xml(data)


class BadRequest(HTTPException):

    code = 400

    def get_response(self, environ):
        return error_response(self.description)


class MissingArgument(BadRequest):

    def __init__(self, name):
        description = "Missing argument '%s'" % (name,)
        BadRequest.__init__(self, description)


class LookupHandler(Handler):

    def __init__(self, conn, fingerprint_data):
        self.conn = conn
        self.fingerprint_data = fingerprint_data

    def _inject_metadata(self, meta, result_map):
        track_mbid_map = lookup_mbids(self.conn, result_map.keys())
        if meta > 1:
            all_mbids = []
            for track_id, mbids in track_mbid_map.iteritems():
                all_mbids.extend(mbids)
            track_meta_map = lookup_metadata(self.conn, all_mbids)
        for track_id, mbids in track_mbid_map.iteritems():
            result = result_map[track_id]
            result['tracks'] = tracks = []
            for mbid in mbids:
                track = {}
                tracks.append(track)
                track['id'] = str(mbid)
                if meta == 1:
                    continue
                track_meta = track_meta_map[mbid]
                track['name'] = track_meta['name']
                track['length'] = track_meta['length']
                track['artist'] = artist = {}
                artist['id'] = track_meta['artist_id']
                artist['name'] = track_meta['artist_name']
                track['release'] = release = {}
                release['id'] = track_meta['release_id']
                release['name'] = track_meta['release_name']
                release['track-num'] = track_meta['track_num']
                release['track-count'] = track_meta['total_tracks']

    def handle(self, req):
        fingerprint_string = req.values.get('fingerprint')
        if not fingerprint_string:
            raise MissingArgument('fingerprint')
        fingerprint, version = chromaprint.decode_fingerprint(fingerprint_string)
        if version != 1:
            raise BadRequest('Unsupported fingerprint version')
        length = req.values.get('length', type=int)
        if not length:
            raise MissingArgument('length')
        meta = req.values.get('meta', type=int, default=0)
        response = {'status': 'ok'}
        response['results'] = results = []
        matches = self.fingerprint_data.search(fingerprint, length, 0.7, 0.3)
        result_map = {}
        for fingerprint_id, track_id, score in matches:
            if track_id in result_map:
                continue
            result_map[track_id] = result = {'id': track_id, 'score': score}
            results.append(result)
        if meta and result_map:
            self._inject_metadata(meta, result_map)
        return serialize_response(response, req.values.get('format'))

    @classmethod
    def create_from_server(cls, server):
        conn = server.engine.connect()
        return cls(conn, FingerprintData(conn))


def iter_args_suffixes(args, prefix):
    prefix_dot = prefix + '.'
    for name in args.iterkeys():
        if name == prefix:
            yield ''
        elif name.startswith(prefix_dot):
            prefix, suffix = name.split('.', 1)
            if suffix.isdigit():
                yield '.' + suffix

class SubmitHandler(Handler):

    def __init__(self, conn):
        self.conn = conn

    def _read_fp_params(self, args, suffix):
        def read_arg(name):
            if name + suffix in args:
                return args[name + suffix]
        p = {}
        p['puid'] = read_arg('puid')
        p['mbids'] = [read_arg('mbid')]
        p['length'] = read_arg('length')
        p['fingerprint'] = chromaprint.decode_fingerprint(read_arg('fingerprint'))[0]
        p['bitrate'] = read_arg('bitrate')
        p['format'] = read_arg('format')
        return p

    def handle(self, req):
        params = []
        for suffix in iter_args_suffixes(req.values, 'fingerprint'):
            params.append(self._read_fp_params(req.values, suffix))
        application_apikey = req.values['client']
        application_id = lookup_application_id_by_apikey(self.conn, application_apikey)
        account_apikey = req.values['user']
        account_id = lookup_account_id_by_apikey(self.conn, account_apikey)
        source_id = find_or_insert_source(self.conn, application_id, account_id)
        user = req.values['user']
        with self.conn.begin():
            format_ids = {}
            for p in params:
                if p['format'] and p['format'] not in format_ids:
                    format_ids[p['format']] = find_or_insert_format(self.conn, p['format'])
            for p in params:
                for mbid in p['mbids']:
                    insert_submission(self.conn, {
                        'mbid': mbid,
                        'puid': p['puid'],
                        'bitrate': p['bitrate'],
                        'fingerprint': p['fingerprint'],
                        'length': p['length'],
                        'format_id': format_ids[p['format']] if p['format'] else None,
                        'source_id': source_id
                    })
        response = {'status': 'ok'}
        return serialize_response(response, req.values.get('format'))

    @classmethod
    def create_from_server(cls, server):
        conn = server.engine.connect()
        return cls(conn)

