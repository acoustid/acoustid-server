# Copyright (C) 2011,2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables as schema
from acoustid.data.account import insert_account, lookup_account_id_by_apikey
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
        query = sql.select([schema.track.c.gid],
            schema.track_puid.c.puid == params.puid,
            schema.track_puid.join(schema.track))
        for row in self.conn.execute(query):
            tracks.append({'id': row['gid']})
        return response


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

