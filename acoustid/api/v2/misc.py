# Copyright (C) 2011,2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import datetime
import logging
from typing import Any
from urllib.parse import urlparse

import requests
from redis.exceptions import RedisError
from sqlalchemy import String, sql
from werkzeug.datastructures import MultiDict

from acoustid import const
from acoustid import tables as schema
from acoustid.api import errors
from acoustid.api.v2 import APIHandler, APIHandlerParams
from acoustid.data.account import (
    count_pending_link_requests,
    create_user_key_link_request,
    format_link_code,
    get_account_details_by_mbuser,
    get_user_key_status,
    insert_account,
    lookup_account_id_by_apikey,
    refresh_cached_user_key,
)
from acoustid.db import DatabaseContext
from acoustid.utils import is_uuid

logger = logging.getLogger(__name__)


class TrackListByMBIDHandlerParams(APIHandlerParams):
    def parse(self, values, db):
        super(TrackListByMBIDHandlerParams, self).parse(values, db)
        self.disabled = values.get("disabled", type=int)
        self.batch = values.get("batch", type=int)
        self.mbids = values.getlist("mbid")
        if not self.mbids:
            raise errors.MissingParameterError("mbid")
        if not all(map(is_uuid, self.mbids)):
            raise errors.InvalidUUIDError("mbid")


class TrackListByMBIDHandler(APIHandler):
    params_class = TrackListByMBIDHandlerParams

    def _handle_internal(self, params):
        response = {}
        query = (
            sql.select(
                sql.cast(schema.track_mbid.c.mbid, String).label("mbid"),
                schema.track_mbid.c.disabled,
                sql.cast(schema.track.c.gid, String).label("gid"),
            )
            .where(schema.track_mbid.c.mbid.in_(params.mbids))
            .select_from(schema.track_mbid.join(schema.track))
        )
        if not params.disabled:
            query = query.where(schema.track_mbid.c.disabled.is_(False))

        tracks_map: dict[str, list[dict[str, int | bool]]] = {}
        fingerprint_db = self.ctx.db.get_fingerprint_db(read_only=True)
        for mbid, disabled, track_gid in fingerprint_db.execute(query):
            track = {"id": track_gid}
            if params.disabled and disabled:
                track["disabled"] = disabled
            tracks_map.setdefault(mbid, []).append(track)
        if not params.batch:
            response["tracks"] = tracks_map.get(params.mbids[0], [])
        else:
            response["mbids"] = mbids = []
            for mbid in params.mbids:
                mbids.append(
                    {
                        "mbid": mbid,
                        "tracks": tracks_map.get(mbid, []),
                    }
                )
        return response


class TrackListByPUIDHandlerParams(APIHandlerParams):
    def parse(self, values, db):
        super(TrackListByPUIDHandlerParams, self).parse(values, db)
        self.puid = values.get("puid")
        if not self.puid:
            raise errors.MissingParameterError("puid")
        if not is_uuid(self.puid):
            raise errors.InvalidUUIDError("puid")


class TrackListByPUIDHandler(APIHandler):
    params_class = TrackListByPUIDHandlerParams

    def _handle_internal(self, params):
        response: dict[str, list] = {}
        response["tracks"] = []
        return response


class UserCreateMusicBrainzHandlerParams(APIHandlerParams):
    def parse(self, values, db):
        super(UserCreateMusicBrainzHandlerParams, self).parse(values, db)
        self.access_token = values.get("access_token")
        if not self.access_token:
            raise errors.MissingParameterError("access_token")


class UserCreateMusicBrainzHandler(APIHandler):
    params_class = UserCreateMusicBrainzHandlerParams

    def _handle_internal(self, params):
        if not self.is_secure:
            raise errors.InsecureRequestError()
        resp = requests.get(
            "https://musicbrainz.org/oauth2/userinfo",
            params={"access_token": params.access_token},
        )
        if resp.status_code != requests.codes.ok:
            raise errors.InvalidMusicBrainzAccessTokenError()
        mbuser = resp.json()["sub"]
        app_db = self.ctx.db.get_app_db()
        account = get_account_details_by_mbuser(app_db, mbuser)
        if account is not None:
            api_key = account["apikey"]
        else:
            id, api_key = insert_account(
                app_db,
                {
                    "name": mbuser,
                    "mbuser": mbuser,
                    "created_from": self.user_ip,
                },
            )
        result = {"user": {"apikey": api_key}}
        self.ctx.db.session.commit()
        return result


class UserCreateAnonymousHandlerParams(APIHandlerParams):
    def parse(self, values, db):
        super(UserCreateAnonymousHandlerParams, self).parse(values, db)
        self._parse_client(values, db)


class UserCreateAnonymousHandler(APIHandler):
    params_class = UserCreateAnonymousHandlerParams

    def _handle_internal(self, params):
        id, api_key = insert_account(
            self.ctx.db.get_app_db(),
            {
                "name": "Anonymous",
                "created_from": self.user_ip,
                "application_id": params.application_id,
                "application_version": params.application_version,
            },
        )
        result = {"user": {"apikey": api_key}}
        self.ctx.db.session.commit()
        return result


MAX_DEVICE_LENGTH = 100
MAX_RETURN_URL_LENGTH = 2000


class UserRequestLinkHandlerParams(APIHandlerParams):
    def parse(self, values: MultiDict, db: DatabaseContext) -> None:
        super().parse(values, db)
        self._parse_client(values, db)
        self.device: str | None = values.get("device", "").strip() or None
        if self.device is not None and len(self.device) > MAX_DEVICE_LENGTH:
            raise errors.InvalidParameterError(
                "device", "must be at most %d characters" % MAX_DEVICE_LENGTH
            )
        self.return_url: str | None = values.get("return_url", "").strip() or None
        if self.return_url is not None:
            url = urlparse(self.return_url)
            if url.scheme not in ("http", "https") or not url.netloc:
                raise errors.InvalidParameterError(
                    "return_url", "must be an http or https URL"
                )
            if len(self.return_url) > MAX_RETURN_URL_LENGTH:
                raise errors.InvalidParameterError(
                    "return_url",
                    "must be at most %d characters" % MAX_RETURN_URL_LENGTH,
                )


class UserRequestLinkHandler(APIHandler):
    """Start linking a user key to an account: the key is returned now, and
    works once someone approves it at the returned URL."""

    params_class = UserRequestLinkHandlerParams

    def _handle_internal(self, params: APIHandlerParams) -> dict[str, Any]:
        assert isinstance(params, UserRequestLinkHandlerParams)
        self._check_link_request_limit()
        app_db = self.ctx.db.get_app_db()
        if (
            count_pending_link_requests(app_db, params.application_id)
            >= const.USER_KEY_MAX_PENDING_LINKS_PER_APPLICATION
        ):
            logger.warning(
                "Too many pending link requests for application %s",
                params.application_id,
            )
            raise errors.TooManyLinkRequestsError()
        req = create_user_key_link_request(
            app_db, params.application_id, params.device, params.return_url
        )
        self.ctx.db.session.commit()
        refresh_cached_user_key(self.ctx.redis, self.ctx.db.get_app_db(), req.apikey)
        code = format_link_code(req.link_code)
        base_url = self.ctx.config.website.base_url.rstrip("/")
        return {
            "user": {
                "apikey": req.apikey,
                "link": {
                    "code": code,
                    "url": "%s/link?code=%s" % (base_url, code),
                    "expires": req.link_expires.isoformat(),
                },
            }
        }

    def _check_link_request_limit(self) -> None:
        hour = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H")
        key = "linkreq:%s:%s" % (self.user_ip, hour)
        try:
            count = self.ctx.redis.incr(key)
            self.ctx.redis.expire(key, 3600)
        except RedisError:
            logger.warning("Failed to check link request limit", exc_info=True)
            return
        if count > const.USER_KEY_LINK_REQUESTS_PER_IP_PER_HOUR:
            raise errors.TooManyLinkRequestsError()


class UserLinkStatusHandlerParams(APIHandlerParams):
    def parse(self, values: MultiDict, db: DatabaseContext) -> None:
        super().parse(values, db)
        self._parse_client(values, db)
        self.user_apikey: str = values.get("user", "")
        if not self.user_apikey:
            raise errors.MissingParameterError("user")


class UserLinkStatusHandler(APIHandler):
    """The state of a user key, so a client can tell waiting from starting over.

    Read from the database rather than the cache: this is what a client polls
    while the user approves.
    """

    params_class = UserLinkStatusHandlerParams

    def _handle_internal(self, params: APIHandlerParams) -> dict[str, Any]:
        assert isinstance(params, UserLinkStatusHandlerParams)
        status = get_user_key_status(self.ctx.db.get_app_db(), params.user_apikey)
        if status is None:
            return {"key": {"state": "unknown"}}
        result: dict[str, Any] = {"state": status.state}
        if status.expires is not None:
            result["expires"] = status.expires.isoformat()
        return {"key": result}


class UserLookupHandlerParams(APIHandlerParams):
    def parse(self, values, db):
        super(UserLookupHandlerParams, self).parse(values, db)
        account_apikey = values.get("user")
        if not account_apikey:
            raise errors.MissingParameterError("user")
        self.account_id = lookup_account_id_by_apikey(db.get_app_db(), account_apikey)
        if not self.account_id:
            raise errors.InvalidUserAPIKeyError()
        self.account_apikey = account_apikey


class UserLookupHandler(APIHandler):
    params_class = UserLookupHandlerParams

    def _handle_internal(self, params):
        return {"user": {"apikey": params.account_apikey}}


class GetFingerprintHandlerParams(APIHandlerParams):
    def parse(self, values, db):
        super(GetFingerprintHandlerParams, self).parse(values, db)
        self.fingerprint_id = values.get("id", type=int)
        if not self.fingerprint_id:
            raise errors.MissingParameterError("id")


class GetFingerprintHandler(APIHandler):
    params_class = GetFingerprintHandlerParams

    def _handle_internal(self, params):
        from acoustid.models import Fingerprint

        fingerprint = (
            self.ctx.db.session.query(Fingerprint)
            .filter_by(id=params.fingerprint_id)
            .first()
        )
        if fingerprint is None:
            raise errors.FingerprintNotFoundError()
        return {
            "fingerprint": {
                "id": fingerprint.id,
                "hashes": fingerprint.fingerprint,
                "duration": fingerprint.length,
            }
        }
