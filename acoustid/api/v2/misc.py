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
from acoustid.utils import is_uuid

logger = logging.getLogger(__name__)


class TrackListByMBIDHandlerParams(APIHandlerParams):

    def parse(self, values, db):
        super(TrackListByMBIDHandlerParams, self).parse(values, db)
        self.disabled = values.get('disabled', type=int)
        self.batch = values.get('batch', type=int)
        self.mbids = values.getlist('mbid')
        if not self.mbids:
            raise errors.MissingParameterError('mbid')
        if not all(map(is_uuid, self.mbids)):
            raise errors.InvalidUUIDError('mbid')


class TrackListByMBIDHandler(APIHandler):

    params_class = TrackListByMBIDHandlerParams

    def _handle_internal(self, params):
        response = {}
        condition = schema.track_mbid.c.mbid.in_(params.mbids)
        if not params.disabled:
            condition = sql.and_(condition, schema.track_mbid.c.disabled == False)  # noqa: F712
        query = sql.select([schema.track_mbid.c.mbid, schema.track_mbid.c.disabled, schema.track.c.gid],
            condition, schema.track_mbid.join(schema.track))
        tracks_map = {}
        fingerprint_db = self.ctx.db.get_fingerprint_db(read_only=True)
        for mbid, disabled, track_gid in fingerprint_db.execute(query):
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

    def parse(self, values, db):
        super(TrackListByPUIDHandlerParams, self).parse(values, db)
        self.puid = values.get('puid')
        if not self.puid:
            raise errors.MissingParameterError('puid')
        if not is_uuid(self.puid):
            raise errors.InvalidUUIDError('puid')


class TrackListByPUIDHandler(APIHandler):

    params_class = TrackListByPUIDHandlerParams

    def _handle_internal(self, params):
        response = {}
        response['tracks'] = []
        return response


class UserCreateMusicBrainzHandlerParams(APIHandlerParams):

    def parse(self, values, db):
        super(UserCreateMusicBrainzHandlerParams, self).parse(values, db)
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
        app_db = self.ctx.db.get_app_db()
        account = get_account_details_by_mbuser(app_db, mbuser)
        if account is not None:
            api_key = account['apikey']
        else:
            id, api_key = insert_account(app_db, {
                'name': mbuser,
                'mbuser': mbuser,
                'created_from': self.user_ip,
            })
        return {'user': {'apikey': api_key}}


class UserCreateAnonymousHandlerParams(APIHandlerParams):

    def parse(self, values, db):
        super(UserCreateAnonymousHandlerParams, self).parse(values, db)
        self._parse_client(values, db)


class UserCreateAnonymousHandler(APIHandler):

    params_class = UserCreateAnonymousHandlerParams

    def _handle_internal(self, params):
        id, api_key = insert_account(self.ctx.db.get_app_db(), {
            'name': 'Anonymous',
            'created_from': self.user_ip,
            'application_id': params.application_id,
            'application_version': params.application_version,
        })
        return {'user': {'apikey': api_key}}


class UserLookupHandlerParams(APIHandlerParams):

    def parse(self, values, db):
        super(UserLookupHandlerParams, self).parse(values, db)
        account_apikey = values.get('user')
        if not account_apikey:
            raise errors.MissingParameterError('user')
        self.account_id = lookup_account_id_by_apikey(db.get_app_db(), account_apikey)
        if not self.account_id:
            raise errors.InvalidUserAPIKeyError()
        self.account_apikey = account_apikey


class UserLookupHandler(APIHandler):

    params_class = UserLookupHandlerParams

    def _handle_internal(self, params):
        return {'user': {'apikey': params.account_apikey}}


class GetFingerprintHandlerParams(APIHandlerParams):

    def parse(self, values, db):
        super(GetFingerprintHandlerParams, self).parse(values, db)
        self.fingerprint_id = values.get('id', type=int)
        if not self.fingerprint_id:
            raise errors.MissingParameterError('id')


class GetFingerprintHandler(APIHandler):

    params_class = GetFingerprintHandlerParams

    def _handle_internal(self, params):
        from acoustid.models import Fingerprint
        fingerprint = self.ctx.db.session.query(Fingerprint).filter_by(id=params.fingerprint_id).first()
        if fingerprint is None:
            raise errors.FingerprintNotFoundError()
        return {'fingerprint': {
            'id': fingerprint.id,
            'hashes': fingerprint.fingerprint,
            'duration': fingerprint.length,
        }}
