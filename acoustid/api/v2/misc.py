# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import logging
from sqlalchemy import sql
from acoustid import tables as schema
from acoustid.api import errors
from acoustid.api.v2 import APIHandler, APIHandlerParams
from acoustid.handler import Handler, Response
from acoustid.utils import is_uuid, is_foreignid

logger = logging.getLogger(__name__)


class TrackListByMBIDHandlerParams(APIHandlerParams):

    def parse(self, values, conn):
        super(TrackListByMBIDHandlerParams, self).parse(values, conn)
        self.mbid = values.get('mbid')
        if not self.mbid:
            raise errors.MissingParameterError('mbid')
        if not is_uuid(self.mbid):
            raise errors.InvalidUUIDError('mbid')


class TrackListByMBIDHandler(APIHandler):

    params_class = TrackListByMBIDHandlerParams

    def _handle_internal(self, params):
        response = {}
        response['tracks'] = tracks = []
        query = sql.select([schema.track.c.gid],
            schema.track_mbid.c.mbid == params.mbid,
            schema.track_mbid.join(schema.track))
        for row in self.conn.execute(query):
            tracks.append({'id': row['gid']})
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

