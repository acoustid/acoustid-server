# Copyright (C) 2011,2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
import requests
from sqlalchemy import sql
from acoustid import tables as schema
from acoustid.data.account import (
    insert_account, lookup_account_id_by_apikey,
    get_account_details_by_mbuser,
)
from acoustid.api import errors
from acoustid.api.v2 import APIHandler, APIHandlerParams
from acoustid.handler import Handler, Response
from acoustid.utils import is_uuid, is_foreignid

logger = logging.getLogger(__name__)


class TrackListByMBIDHandlerParams(APIHandlerParams):

    def parse(self, values, conn):
        super(TrackListByMBIDHandlerParams, self).parse(values, conn)
        self.disabled = values.get('disabled', type=int)
        self.batch = values.get('batch', type=int)
        self.mbids = values.getlist('mbid')
        if not self.mbids:
            raise errors.MissingParameterError('mbid')
        if not all(map(is_uuid, self.mbids)):
            raise errors.InvalidUUIDError('mbid' + suffix)


class TrackListByMBIDHandler(APIHandler):

    params_class = TrackListByMBIDHandlerParams

    def _handle_internal(self, params):
        response = {}
        condition = schema.track_mbid.c.mbid.in_(params.mbids)
        if not params.disabled:
            condition = sql.and_(condition, schema.track_mbid.c.disabled == False)
        query = sql.select([schema.track_mbid.c.mbid, schema.track_mbid.c.disabled, schema.track.c.gid],
            condition, schema.track_mbid.join(schema.track))
        tracks_map = {}
        for mbid, disabled, track_gid in self.conn.execute(query):
            track = {'id': track_gid}
            if params.disabled and disabled:
                track['disabled'] = disabled
            tracks_map.setdefault(mbid, []).append(track)
        if not params.batch:
            response['tracks'] = tracks_map.get(params.mbids[0], [])
        else:
            response['mbids'] = mbids = []
            for mbid in params.mbids:
                mbids.append({
                    'mbid': mbid,
                    'tracks': tracks_map.get(mbid, []),
                })
        return response


class TrackListByPUIDHandlerParams(APIHandlerParams):

    def parse(self, values, conn):
        super(TrackListByPUIDHandlerParams, self).parse(values, conn)
        self.puid = values.get('puid')
        if not self.puid:
            raise errors.MissingParameterError('puid')
        if not is_uuid(self.puid):
            raise errors.InvalidUUIDError('puid')


class TrackListByPUIDHandler(APIHandler):

    params_class = TrackListByPUIDHandlerParams

    def _handle_internal(self, params):
        response = {}
        response['tracks'] = tracks = []
        return response


class UserCreateMusicBrainzHandlerParams(APIHandlerParams):

    def parse(self, values, conn):
        super(UserCreateMusicBrainzHandlerParams, self).parse(values, conn)
        self.access_token = values.get('access_token')
        if not self.access_token:
            raise errors.MissingParameterError('access_token')


class UserCreateMusicBrainzHandler(APIHandler):

    params_class = UserCreateMusicBrainzHandlerParams

    def _handle_internal(self, params):
        if not self.is_secure:
            raise errors.InsecureRequestError()
        resp = requests.get('https://musicbrainz.org/oauth2/userinfo',
            params={'access_token': params.access_token})
        if resp.status_code != requests.codes.ok:
            raise errors.InvalidMusicBrainzAccessTokenError()
        mbuser = resp.json()['sub']
        account = get_account_details_by_mbuser(self.conn, mbuser)
        if account is not None:
            api_key = account['apikey']
        else:
            id, api_key = insert_account(self.conn, {
                'name': mbuser,
                'mbuser': mbuser,
                'created_from': self.user_ip,
            })
        return {'user': {'apikey': api_key}}


class UserCreateAnonymousHandlerParams(APIHandlerParams):

    def parse(self, values, conn):
        super(UserCreateAnonymousHandlerParams, self).parse(values, conn)
        self._parse_client(values, conn)


class UserCreateAnonymousHandler(APIHandler):

    params_class = UserCreateAnonymousHandlerParams

    def _handle_internal(self, params):
        print {
            'name': 'Anonymous',
            'created_from': self.user_ip,
            'application_id': params.application_id,
            'application_version': params.application_version,
        }
        id, api_key = insert_account(self.conn, {
            'name': 'Anonymous',
            'created_from': self.user_ip,
            'application_id': params.application_id,
            'application_version': params.application_version,
        })
        return {'user': {'apikey': api_key}}


class UserLookupHandlerParams(APIHandlerParams):

    def parse(self, values, conn):
        super(UserLookupHandlerParams, self).parse(values, conn)
        account_apikey = values.get('user')
        if not account_apikey:
            raise errors.MissingParameterError('user')
        self.account_id = lookup_account_id_by_apikey(conn, account_apikey)
        if not self.account_id:
            raise errors.InvalidUserAPIKeyError()
        self.account_apikey = account_apikey


class UserLookupHandler(APIHandler):

    params_class = UserLookupHandlerParams

    def _handle_internal(self, params):
        return {'user': {'apikey': params.account_apikey}}

