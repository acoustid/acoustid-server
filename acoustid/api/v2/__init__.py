# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import contextvars
import json
import uuid
import logging
import operator
import re
import time
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
)

import attr
import cachetools
from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from werkzeug.wrappers import Request, Response

from acoustid import const
from acoustid.api import errors, serialize_response
from acoustid.const import MAX_REQUESTS_PER_SECOND
from acoustid.data.account import lookup_account_id_by_apikey
from acoustid.data.application import lookup_application_id_by_apikey
from acoustid.data.fingerprint import (
    FingerprintMatch,
    FingerprintSearcher,
    decode_fingerprint,
)
from acoustid.data.meta import lookup_meta
from acoustid.data.musicbrainz import lookup_metadata
from acoustid.data.stats import update_lookup_counter, update_user_agent_counter
from acoustid.data.submission import insert_submission, lookup_submission_status
from acoustid.data.track import lookup_mbids, lookup_meta_ids, resolve_track_gid
from acoustid.db import DatabaseContext
from acoustid.handler import Handler
from acoustid.ratelimiter import RateLimiter
from acoustid.tasks import enqueue_task
from acoustid.tracing import initialize_trace_id
from acoustid.utils import check_demo_client_api_key, is_foreignid, is_uuid

if TYPE_CHECKING:
    from acoustid.config import Config

logger = logging.getLogger(__name__)


DEFAULT_FORMAT = "json"
FORMATS = set(["xml", "json", "jsonp"])

DEMO_APPLICATION_ID = 2

MAX_META_IDS_PER_TRACK = 10

MAX_FINGERPRINT_QUERIES_PER_REQUEST = 20  # temporary, decreate to 10 or less later
MAX_TRACK_QUERIES_PER_REQUEST = 100

MAX_RESULTS_PER_FINGERPRINT_QUERY = 10


def iter_args_suffixes(args: dict, *prefixes: str) -> Iterable[str]:
    results: set[int] = set()
    for name in args:
        for prefix in prefixes:
            if name == prefix:
                results.add(-1)
            elif name.startswith(prefix + "."):
                prefix, suffix = name.split(".", 1)
                if suffix.isdigit():
                    results.add(int(suffix))
    return [f".{i}" if i != -1 else "" for i in sorted(results)]


api_key_cache = cachetools.TTLCache(maxsize=1000, ttl=60.0)  # type: cachetools.Cache


def check_app_api_key_cache_key(config, db, application_apikey):
    return application_apikey


@cachetools.cached(api_key_cache, key=check_app_api_key_cache_key)
def check_app_api_key(config, db, application_apikey):
    app_db = db.get_app_db(read_only=True)
    application_id = lookup_application_id_by_apikey(
        app_db, application_apikey, only_active=True
    )
    if not application_id:
        if check_demo_client_api_key(config.website.secret, application_apikey):
            application_id = DEMO_APPLICATION_ID
    return application_id


def user_api_key_cache_key(config, db, user_apikey):
    return user_apikey


@cachetools.cached(api_key_cache, key=check_app_api_key_cache_key)
def check_user_api_key(config, db, user_apikey):
    app_db = db.get_app_db(read_only=True)
    return lookup_account_id_by_apikey(app_db, user_apikey)


class APIHandlerParams(object):
    def __init__(self, config):
        # type: (Config) -> None
        self.config = config
        self.format = DEFAULT_FORMAT

    def _parse_client(self, values, db):
        application_apikey = values.get("client")
        if not application_apikey:
            raise errors.MissingParameterError("client")
        self.application_id = check_app_api_key(self.config, db, application_apikey)
        if not self.application_id:
            logger.warning("Invalid API key %s", application_apikey)
            raise errors.InvalidAPIKeyError()
        self.application_version = values.get("clientversion")

    def _parse_format(self, values):
        self.format = values.get("format", DEFAULT_FORMAT)
        if self.format not in FORMATS:
            self.format = DEFAULT_FORMAT  # used for the error response
            raise errors.UnknownFormatError(self.format)
        if self.format == "jsonp":
            callback = values.get("jsoncallback", "jsonAcoustidApi")
            if not re.match(
                r"^[$A-Za-z_][0-9A-Za-z_]*(\.[$A-Za-z_][0-9A-Za-z_]*)*$", callback
            ):
                callback = "jsonAcoustidApi"
            self.format = "%s:%s" % (self.format, callback)

    def parse(self, values, db):
        self._parse_format(values)


DEFAULT_APPLICATION_RATE_LIMIT = 10


class APIHandler(Handler):
    params_class = None  # type: Type[APIHandlerParams]

    def _error(self, code, message, format=DEFAULT_FORMAT, status=400):
        # type: (int, str, str, int) -> Response
        response_data = {"status": "error", "error": {"code": code, "message": message}}
        return serialize_response(response_data, format, status=status)

    def _ok(self, data, format=DEFAULT_FORMAT):
        # type: (Dict[str, Any], str) -> Response
        response_data = {"status": "ok"}
        response_data.update(data)
        return serialize_response(response_data, format)

    def _rate_limit(self, user_ip, application_id):
        # type: (str, Optional[int]) -> None

        check_ip_rate_limit = True
        if application_id is not None:
            application_rate_limit = self.ctx.config.rate_limiter.applications.get(
                application_id
            )
            if application_rate_limit is not None:
                check_ip_rate_limit = False
            else:
                application_rate_limit = DEFAULT_APPLICATION_RATE_LIMIT
            if self.rate_limiter.limit(
                "app", str(application_id), application_rate_limit
            ):
                raise errors.TooManyRequests(application_rate_limit)

        global_rate_limit = self.ctx.config.rate_limiter.global_rate_limit
        if global_rate_limit is not None:
            if self.rate_limiter.limit("global", "", global_rate_limit):
                raise errors.TooManyRequests(global_rate_limit)

        if check_ip_rate_limit:
            ip_rate_limit = self.ctx.config.rate_limiter.ips.get(
                user_ip, MAX_REQUESTS_PER_SECOND
            )
            if self.rate_limiter.limit("ip", user_ip, ip_rate_limit):
                raise errors.TooManyRequests(ip_rate_limit)

    def handle(self, req: Request) -> Response:
        ctx = contextvars.copy_context()
        return ctx.run(self._handle_inside_context, req)

    def _handle_inside_context(self, req: Request) -> Response:
        initialize_trace_id()
        params = self.params_class(self.ctx.config)
        if req.access_route:
            self.user_ip = req.access_route[0]
        else:
            self.user_ip = req.remote_addr or "0.0.0.0"
        self.is_secure = req.is_secure
        self.user_agent = req.user_agent
        self.rate_limiter = RateLimiter(self.ctx.redis, "rl")
        request_type = self.__class__.__name__
        try:
            t0 = time.time()
            try:
                try:
                    params.parse(req.values, self.ctx.db)
                    self.ctx.db.session.close()
                    application_id = getattr(params, "application_id", None)
                    if self.ctx.statsd is not None:
                        self.ctx.statsd.incr(
                            "api.requests_total,app={},request={}".format(
                                application_id, request_type
                            )
                        )
                    self._rate_limit(self.user_ip, application_id)
                    return self._ok(self._handle_internal(params), params.format)
                except errors.WebServiceError:
                    raise
                except RequestEntityTooLarge:
                    raise errors.RequestTooLargeError()
                except HTTPException:
                    raise
                except Exception as exc:
                    if self.ctx.statsd is not None:
                        exc_str = str(exc)
                        cause = "unknown"
                        if "redis" in exc_str:
                            cause = "redis"
                        elif "sqlalchemy" in exc_str or "psycopg2" in exc_str:
                            cause = "postgres"
                        self.ctx.statsd.incr(
                            f"api.unhandled_errors_total,request={request_type},cause={cause}"
                        )
                    logger.exception("Error while handling API request")
                    raise errors.InternalError()
            finally:
                t1 = time.time()
                if self.ctx.statsd is not None:
                    self.ctx.statsd.timing(
                        "api.request_duration_seconds,request={}".format(request_type),
                        1000 * (t1 - t0),
                    )
        except errors.WebServiceError as e:
            if self.ctx.statsd is not None:
                self.ctx.statsd.incr(
                    "api.handled_errors_total,code={},request={}".format(
                        e.code_name, request_type
                    )
                )
            return self._error(
                e.code, e.message, getattr(params, "format", "unknown"), status=e.status
            )

    def _handle_internal(self, params):
        # type: (APIHandlerParams) -> Dict[str, Any]
        raise NotImplementedError(self._handle_internal)


@attr.s
class TrackLookupQuery(object):
    index = attr.ib()  # type: Optional[int]
    track_gid = attr.ib()  # type: str


@attr.s
class FingerprintLookupQuery(object):
    index = attr.ib()  # type: Optional[int]
    duration = attr.ib()  # type: int
    fingerprint = attr.ib()  # type: List[int]


class LookupHandlerParams(APIHandlerParams):
    duration_name = "duration"

    def _parse_query(self, values, suffix):
        # type: (MultiDict, str) -> Union[TrackLookupQuery, FingerprintLookupQuery]
        index = int(suffix[1:]) if suffix else None
        track_gid = values.get("trackid" + suffix)
        if track_gid:
            if not is_uuid(track_gid):
                raise errors.InvalidUUIDError("trackid" + suffix)
            return TrackLookupQuery(index=index, track_gid=track_gid)
        else:
            duration = values.get(self.duration_name + suffix, type=int, default=0)
            if not duration:
                raise errors.MissingParameterError(self.duration_name + suffix)
            fingerprint_string = values.get("fingerprint" + suffix)
            if not fingerprint_string:
                raise errors.MissingParameterError("fingerprint" + suffix)
            fingerprint = decode_fingerprint(fingerprint_string)
            if not fingerprint:
                logger.info("Got invalid fingerprint %r", fingerprint_string)
                raise errors.InvalidFingerprintError()
            return FingerprintLookupQuery(
                index=index, duration=duration, fingerprint=fingerprint
            )

    def parse(self, values, db):
        # type: (MultiDict, DatabaseContext) -> None
        super(LookupHandlerParams, self).parse(values, db)
        self._parse_client(values, db)
        self.meta = values.get("meta")
        if self.meta == "0" or not self.meta:
            self.meta = []
        elif self.meta == "1":
            self.meta = ["recordingids"]
        elif self.meta == "2":
            self.meta = ["m2"]
        else:
            self.meta = self.meta.split()
        self.max_duration_diff = values.get("maxdurationdiff", type=int)
        if self.max_duration_diff is None:
            self.max_duration_diff = const.FINGERPRINT_MAX_LENGTH_DIFF
        elif (
            self.max_duration_diff > const.FINGERPRINT_MAX_ALLOWED_LENGTH_DIFF
            or self.max_duration_diff < 1
        ):
            raise errors.InvalidMaxDurationDiffError("maxdurationdiff")
        self.batch = values.get("batch", type=int)
        self.fingerprints = (
            []
        )  # type: List[Union[TrackLookupQuery, FingerprintLookupQuery]]
        suffixes = list(iter_args_suffixes(values, "fingerprint", "trackid"))
        if not suffixes:
            raise errors.MissingParameterError("fingerprint")
        for i, suffix in enumerate(suffixes):
            try:
                self.fingerprints.append(self._parse_query(values, suffix))
            except errors.WebServiceError:
                if not self.fingerprints and i + 1 == len(suffixes):
                    raise


class LookupHandler(APIHandler):
    params_class = LookupHandlerParams
    recordings_name = "recordings"

    def check_for_missing_recordings(
        self, expected_mbids: Iterable[str], meta: List[Dict[str, Any]]
    ) -> None:
        missing_mbids = set(expected_mbids) - set(m["recording_id"] for m in meta)
        if missing_mbids:
            for mbid in missing_mbids:
                logger.warning("Missing metadata for MBID %s", mbid)
                enqueue_task(self.ctx, "merge_missing_mbid", {"mbid": str(mbid)})

    def _inject_recording_ids_internal(self, add=True, add_sources=False):
        # type: (bool, bool) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[int, List[str]]]
        el_recording = {}  # type: Dict[str, List[Dict[str, Any]]]
        res_map = {}  # type: Dict[int, List[str]]
        track_mbid_map = lookup_mbids(
            self.ctx.db.get_fingerprint_db(read_only=True), self.el_result.keys()
        )
        for track_id, mbids in track_mbid_map.items():
            res_map[track_id] = []
            for mbid, sources in mbids:
                res_map[track_id].append(mbid)
                if add:
                    for result_el in self.el_result[track_id]:
                        recording = {"id": str(mbid)}  # type: Dict[str, Any]
                        if add_sources:
                            recording["sources"] = sources
                        result_el.setdefault(self.recordings_name, []).append(recording)
                        el_recording.setdefault(mbid, []).append(recording)
                else:
                    el_recording.setdefault(mbid, []).extend(self.el_result[track_id])
        return el_recording, res_map

    def _inject_user_meta_ids_internal(self, add=True):
        # type: (bool) -> Tuple[Dict[int, List[Dict[str, Any]]], Dict[int, List[int]]]
        el_recording = {}  # type: Dict[int, List[Dict[str, Any]]]
        track_meta_map = lookup_meta_ids(
            self.ctx.db.get_fingerprint_db(read_only=True),
            self.el_result.keys(),
            max_ids_per_track=MAX_META_IDS_PER_TRACK,
        )
        for track_id, meta_ids in track_meta_map.items():
            for meta_id in meta_ids:
                if add:
                    for result_el in self.el_result[track_id]:
                        recording = {}  # type: Dict[str, Any]
                        result_el.setdefault(self.recordings_name, []).append(recording)
                        el_recording.setdefault(meta_id, []).append(recording)
                else:
                    el_recording.setdefault(meta_id, []).extend(
                        self.el_result[track_id]
                    )
        return el_recording, track_meta_map

    def extract_recording(self, m, only_id=False):
        # type: (Dict[str, Any], bool) -> Dict[str, Any]
        recording_id = m["recording_id"]
        if isinstance(recording_id, uuid.UUID):
            recording_id = str(recording_id)
        recording: dict[str, Any] = {"id": recording_id}
        if only_id:
            return recording
        recording["title"] = m["recording_title"] or ""
        if m["recording_duration"]:
            recording["duration"] = float(m["recording_duration"])
        if m["recording_artists"]:
            recording["artists"] = m["recording_artists"]

        return recording

    def extract_release(self, m, only_id=False):
        # type: (Dict[str, Any], bool) -> Dict[str, Any]
        release: dict[str, Any] = {"id": str(m["release_id"])}
        if only_id:
            return release
        release["title"] = m["release_title"] or ""
        if m["release_medium_count"]:
            release["medium_count"] = m["release_medium_count"]
        if m["release_track_count"]:
            release["track_count"] = m["release_track_count"]
        if m["release_artists"]:
            release["artists"] = m["release_artists"]
        if m["release_events"]:
            release["releaseevents"] = []
            for rem in m["release_events"]:
                release_event = {}
                if rem["release_country"]:
                    release_event["country"] = rem["release_country"]
                date = {}
                if rem["release_date_year"]:
                    date["year"] = rem["release_date_year"]
                if rem["release_date_month"]:
                    date["month"] = rem["release_date_month"]
                if rem["release_date_day"]:
                    date["day"] = rem["release_date_day"]
                if date:
                    release_event["date"] = date
                release["releaseevents"].append(release_event)
            release.update(release["releaseevents"][0])
        return release

    def extract_release_group(self, m, only_id=False):
        # type: (Dict[str, Any], bool) -> Dict[str, Any]
        release_group: dict[str, Any] = {"id": str(m["release_group_id"])}
        if only_id:
            return release_group
        release_group["title"] = m["release_group_title"] or ""
        if m["release_group_primary_type"]:
            release_group["type"] = m["release_group_primary_type"]
        if m["release_group_secondary_types"]:
            release_group["secondarytypes"] = m["release_group_secondary_types"]
        if m["release_group_artists"]:
            release_group["artists"] = m["release_group_artists"]
        return release_group

    def _inject_release_groups_internal(self, meta, parent, metadata):
        # type: (List[str], Dict[str, Any], List[Dict[str, Any]]) -> None
        release_groups = self._group_release_groups(metadata, "releasegroupids" in meta)
        parent["releasegroups"] = []
        for release_group, release_group_metadata in release_groups:
            parent["releasegroups"].append(release_group)
            if "releases" in meta or "releaseids" in meta:
                self._inject_releases_internal(
                    meta, release_group, release_group_metadata
                )
                if "compress" in meta:
                    for release in release_group["releases"]:
                        if "artists" in release and release[
                            "artists"
                        ] == release_group.get("artists"):
                            del release["artists"]
                        if "title" in release and release["title"] == release_group.get(
                            "title"
                        ):
                            del release["title"]

    def _inject_releases_internal(self, meta, parent, metadata):
        # type: (List[str], Dict[str, Any], List[Dict[str, Any]]) -> None
        releases = self._group_releases(metadata, "releaseids" in meta)
        parent["releases"] = []
        for release, release_metadata in releases:
            parent["releases"].append(release)
            if "tracks" in meta:
                release["mediums"] = list(self._group_tracks(release_metadata))
                if "compress" in meta:
                    for medium in release["mediums"]:
                        for track in medium["tracks"]:
                            if "artists" in track and track["artists"] == release.get(
                                "artists"
                            ):
                                del track["artists"]

    def inject_recordings(self, meta):
        # type: (List[str]) -> None
        recording_els = self._inject_recording_ids_internal(True, "sources" in meta)[0]
        load_releases = False
        load_release_groups = False
        if "releaseids" in meta or "releases" in meta:
            load_releases = True
        if "releasegroupids" in meta or "releasegroups" in meta:
            load_releases = True
            load_release_groups = True
        metadata = lookup_metadata(
            self.ctx.db.get_musicbrainz_db(read_only=True),
            recording_els.keys(),
            load_releases=load_releases,
            load_release_groups=load_release_groups,
        )
        self.check_for_missing_recordings(recording_els.keys(), metadata)
        if "usermeta" in meta and not metadata:
            user_meta_els = self._inject_user_meta_ids_internal(True)[0]
            recording_els.update(user_meta_els)  # type: ignore
            user_meta = lookup_meta(
                self.ctx.db.get_fingerprint_db(read_only=True), user_meta_els.keys()
            )
            metadata.extend(user_meta)
        for recording, recording_metadata in self._group_recordings(
            metadata, "recordingids" in meta
        ):
            if "releasegroups" in meta or "releasegroupids" in meta:
                self._inject_release_groups_internal(
                    meta, recording, recording_metadata
                )
                if "compress" in meta:
                    for release_group in recording.get("releasegroups", []):
                        for release in release_group.get("releases", []):
                            for medium in release.get("mediums", []):
                                for track in medium["tracks"]:
                                    if "title" in track and track[
                                        "title"
                                    ] == recording.get("title"):
                                        del track["title"]
                    if "artists" in release_group and release_group[
                        "artists"
                    ] == recording.get("artists"):
                        del release_group["artists"]
            elif "releases" in meta or "releaseids" in meta:
                self._inject_releases_internal(meta, recording, recording_metadata)
                if "compress" in meta:
                    for release in recording.get("releases", []):
                        for medium in release.get("mediums", []):
                            for track in medium["tracks"]:
                                if "title" in track and track["title"] == recording.get(
                                    "title"
                                ):
                                    del track["title"]
                        if "artists" in release and release["artists"] == recording.get(
                            "artists"
                        ):
                            del release["artists"]
            for recording_el in recording_els[recording["id"]]:
                if "usermeta" in meta:
                    if isinstance(recording.get("id"), int):
                        del recording["id"]
                        if "title" in recording and not recording["title"]:
                            del recording["title"]
                        if "releasegroups" in recording:
                            releasegroups = []
                            for releasegroup in recording["releasegroups"]:
                                del releasegroup["id"]
                                if (
                                    "title" in releasegroup
                                    and not releasegroup["title"]
                                ):
                                    del releasegroup["title"]
                                if "releases" in releasegroup:
                                    releases = []
                                    for release in releasegroup["releases"]:
                                        del release["id"]
                                        if "title" in release and not release["title"]:
                                            del release["title"]
                                        if release:
                                            releases.append(release)
                                    if releases:
                                        releasegroup["releases"] = releases
                                    else:
                                        del releasegroup["releases"]
                                if releasegroup:
                                    releasegroups.append(releasegroup)
                            if releasegroups:
                                recording["releasegroups"] = releasegroups
                            else:
                                del recording["releasegroups"]
                        if "releases" in recording:
                            releases = []
                            for release in recording["releases"]:
                                del release["id"]
                                if "title" in release and not release["title"]:
                                    del release["title"]
                                if release:
                                    releases.append(release)
                            if releases:
                                recording["releases"] = releases
                            else:
                                del recording["releases"]
                recording_el.update(recording)

    def inject_releases(self, meta):
        # type: (List[str]) -> None
        recording_els, track_mbid_map = self._inject_recording_ids_internal(False)
        metadata = lookup_metadata(
            self.ctx.db.get_musicbrainz_db(read_only=True),
            recording_els.keys(),
            load_releases=True,
            load_release_groups=True,
        )
        self.check_for_missing_recordings(recording_els.keys(), metadata)
        for track_id, track_metadata in self._group_metadata(metadata, track_mbid_map):
            result = {}  # type: Dict[str, Any]
            self._inject_releases_internal(meta, result, track_metadata)
            for result_el in self.el_result[track_id]:
                result_el.update(result)

    def inject_release_groups(self, meta):
        # type: (List[str]) -> None
        recording_els, track_mbid_map = self._inject_recording_ids_internal(False)
        metadata = lookup_metadata(
            self.ctx.db.get_musicbrainz_db(read_only=True),
            recording_els.keys(),
            load_releases=True,
            load_release_groups=True,
        )
        self.check_for_missing_recordings(recording_els.keys(), metadata)
        for track_id, track_metadata in self._group_metadata(metadata, track_mbid_map):
            result = {}  # type: Dict[str, Any]
            self._inject_release_groups_internal(meta, result, track_metadata)
            for result_el in self.el_result[track_id]:
                result_el.update(result)

    def _group_metadata(self, metadata, track_mbid_map):
        # type: (List[Dict[str, Any]], Dict[int, List[str]]) -> Iterable[Tuple[int, List[Dict[str, Any]]]]
        results = {}  # type: Dict[int, List[Dict[str, Any]]]
        for track_id, mbids in track_mbid_map.items():
            mbids_set = set(mbids)
            results[track_id] = []
            for item in metadata:
                if item["recording_id"] in mbids_set:
                    results[track_id].append(item)
        return results.items()

    def _group_release_groups(self, metadata, only_ids=False):
        results: dict[int, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
        for item in metadata:
            id = item["release_group_id"]
            if id not in results:
                results[id] = (self.extract_release_group(item, only_id=only_ids), [])
            results[id][1].append(item)
        return results.values()

    def _group_recordings(self, metadata, only_ids=False):
        results: dict[int, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
        for item in metadata:
            id = item["recording_id"]
            if id not in results:
                results[id] = (self.extract_recording(item, only_id=only_ids), [])
            results[id][1].append(item)
        return results.values()

    def _group_releases(self, metadata, only_ids=False):
        results: dict[int, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
        for item in metadata:
            id = item["release_id"]
            if id not in results:
                results[id] = (self.extract_release(item, only_id=only_ids), [])
            results[id][1].append(item)
        return results.values()

    def _group_tracks(self, metadata):
        results: dict[int, dict[str, Any]] = {}
        for item in metadata:
            medium_pos = item["medium_position"]
            medium = results.get(medium_pos)
            if medium is None:
                medium = {"position": medium_pos, "tracks": []}
                medium["track_count"] = item["medium_track_count"]
                if item["medium_format"]:
                    medium["format"] = item["medium_format"]
                if item["medium_title"]:
                    medium["title"] = item["medium_title"]
                results[medium_pos] = medium
            track = {
                "id": item["track_id"],
                "position": item["track_position"],
                "title": item["track_title"],
                "artists": item["track_artists"],
            }
            medium["tracks"].append(track)
        return results.values()

    def inject_m2(self, meta):
        el_recording = self._inject_recording_ids_internal(True)[0]
        metadata = lookup_metadata(
            self.ctx.db.get_musicbrainz_db(read_only=True),
            el_recording.keys(),
            load_releases=True,
        )
        self.check_for_missing_recordings(el_recording.keys(), metadata)
        last_recording_id = None
        for item in metadata:
            if last_recording_id != item["recording_id"]:
                recording = self.extract_recording(item, True)
                last_recording_id = item["recording_id"]
                for el in el_recording[last_recording_id]:
                    if item["recording_duration"]:
                        recording["duration"] = float(item["recording_duration"])
                    recording["tracks"] = []
                    el.update(recording)
        metadata = sorted(
            metadata,
            key=operator.itemgetter(
                "recording_id", "release_id", "medium_position", "track_position"
            ),
        )
        for item in metadata:
            for el in el_recording[item["recording_id"]]:
                medium = {
                    "track_count": item["medium_track_count"],
                    "position": item["medium_position"],
                    "release": {
                        "id": item["release_id"],
                        "title": item["release_title"],
                    },
                }
                if item["medium_format"]:
                    medium["format"] = item["medium_format"]
                el["tracks"].append(
                    {
                        "title": item["track_title"],
                        "duration": float(item["track_duration"]),
                        "artists": item["track_artists"],
                        "position": item["track_position"],
                        "medium": medium,
                    }
                )

    def inject_metadata(self, meta, result_map):
        self.el_result = result_map
        if "m2" in meta:
            self.inject_m2(meta)
        elif "recordings" in meta or "recordingids" in meta:
            self.inject_recordings(meta)
        elif "releasegroups" in meta or "releasegroupids" in meta:
            self.inject_release_groups(meta)
        elif "releases" in meta or "releaseids" in meta:
            self.inject_releases(meta)

    def _inject_results(self, results, result_map, matches):
        seen = set()
        for fingerprint_id, track_id, track_gid, score in matches:
            if track_id in seen:
                continue
            seen.add(track_id)
            result = {"id": str(track_gid), "score": score}
            result_map.setdefault(track_id, []).append(result)
            results.append(result)
        return seen

    def _handle_internal(self, params):
        # type: (APIHandlerParams) -> Dict[str, Any]
        assert isinstance(params, LookupHandlerParams)

        if self.ctx.statsd is not None:
            statsd = self.ctx.statsd.pipeline()
        else:
            statsd = None

        update_user_agent_counter(
            self.ctx.redis, params.application_id, str(self.user_agent), self.user_ip
        )

        assert params.max_duration_diff is not None

        if params.batch:
            fingerprints = params.fingerprints
        else:
            fingerprints = params.fingerprints[:1]

        num_fingerprint_queries = 0
        num_track_queries = 0

        for p in fingerprints:
            if isinstance(p, TrackLookupQuery):
                num_track_queries += 1
            elif isinstance(p, FingerprintLookupQuery):
                num_fingerprint_queries += 1

        if num_fingerprint_queries > MAX_FINGERPRINT_QUERIES_PER_REQUEST:
            raise errors.RequestTooLargeError()

        if num_track_queries > MAX_TRACK_QUERIES_PER_REQUEST:
            raise errors.RequestTooLargeError()

        all_matches = []
        for p in fingerprints:
            if isinstance(p, TrackLookupQuery):
                track_id = resolve_track_gid(
                    self.ctx.db.get_fingerprint_db(read_only=True), p.track_gid
                )
                if track_id:
                    matches = [
                        FingerprintMatch(
                            fingerprint_id=0,
                            track_id=track_id,
                            track_gid=p.track_gid,
                            score=1.0,
                        )
                    ]
                else:
                    matches = []
            elif isinstance(p, FingerprintLookupQuery):
                searcher = FingerprintSearcher(
                    db=self.ctx.db.get_fingerprint_db(read_only=True),
                    index_pool=self.ctx.index,
                    fpstore=self.ctx.fpstore,
                    timeout=self.ctx.config.website.search_timeout,
                )
                searcher.max_length_diff = params.max_duration_diff
                matches = searcher.search(
                    p.fingerprint,
                    p.duration,
                    max_results=MAX_RESULTS_PER_FINGERPRINT_QUERY,
                )
                self.ctx.db.session.close()
                if statsd is not None:
                    statsd.incr("api.lookup.searches.total")
                    statsd.incr("api.lookup.matches.total", len(matches))
            all_matches.append(matches)

        self.ctx.db.session.close()

        response = {}  # type: Dict[str, Any]
        if params.batch:
            response["fingerprints"] = fps = []
            result_map = {}  # type: ignore
            for p, matches in zip(fingerprints, all_matches):
                results = []  # type: ignore
                fps.append({"index": p.index, "results": results})
                track_ids = self._inject_results(results, result_map, matches)
                update_lookup_counter(
                    self.ctx.redis, params.application_id, bool(track_ids)
                )
                logger.debug(
                    "Lookup from %s: %s", params.application_id, list(track_ids)
                )
        else:
            response["results"] = results = []
            result_map = {}
            self._inject_results(results, result_map, all_matches[0])
            update_lookup_counter(
                self.ctx.redis, params.application_id, bool(result_map)
            )
            logger.debug("Lookup from %s: %s", params.application_id, result_map.keys())

        if self.ctx.config.website.search_return_metadata:
            if params.meta and result_map:
                self.inject_metadata(params.meta, result_map)

        if statsd is not None:
            statsd.send()

        return response


class SubmissionStatusHandlerParams(APIHandlerParams):
    def parse(self, values, db):
        # type: (MultiDict, DatabaseContext) -> None
        super(SubmissionStatusHandlerParams, self).parse(values, db)
        self._parse_client(values, db)
        self.ids = values.getlist("id", type=int)


class SubmissionStatusHandler(APIHandler):
    params_class = SubmissionStatusHandlerParams

    def _handle_internal(self, params: APIHandlerParams) -> Dict[str, Any]:
        assert isinstance(params, SubmissionStatusHandlerParams)
        response = {
            "submissions": [
                {"id": submission_id, "status": "pending"}
                for submission_id in params.ids
            ]
        }
        tracks = lookup_submission_status(
            self.ctx.db.get_ingest_db(read_only=True),
            self.ctx.db.get_fingerprint_db(read_only=True),
            params.ids,
        )
        for submission in response["submissions"]:
            submission_id = submission["id"]
            assert isinstance(submission_id, int)
            track_gid = tracks.get(submission_id)
            if track_gid is not None:
                submission["status"] = "imported"
                submission["result"] = {"id": str(track_gid)}
        return response


class SubmitHandlerParams(APIHandlerParams):
    def _parse_user(self, values, db):
        # type: (MultiDict, DatabaseContext) -> None
        account_apikey = values.get("user")
        if not account_apikey:
            raise errors.MissingParameterError("user")
        self.account_id = check_user_api_key(self.config, db, account_apikey)
        if not self.account_id:
            raise errors.InvalidUserAPIKeyError()

    def _parse_duration_and_format(self, p, values, suffix):
        # type: (Dict[str, Any], MultiDict, str) -> None
        p["duration"] = values.get("duration" + suffix, type=int)
        if p["duration"] is None:
            raise errors.MissingParameterError("duration" + suffix)
        if p["duration"] <= 0 or p["duration"] > 0x7FFF:
            raise errors.InvalidDurationError("duration" + suffix)
        p["format"] = values.get("fileformat" + suffix)

    def _parse_submission(self, values, suffix):
        # type: (MultiDict, str) -> None
        p = {}  # type: Dict[str, Any]
        p["index"] = (suffix or "")[1:]
        p["puid"] = values.get("puid" + suffix)
        if p["puid"] and not is_uuid(p["puid"]):
            raise errors.InvalidUUIDError("puid" + suffix)
        p["foreignid"] = values.get("foreignid" + suffix)
        if p["foreignid"] and not is_foreignid(p["foreignid"]):
            raise errors.InvalidForeignIDError("foreignid" + suffix)
        p["mbids"] = values.getlist("mbid" + suffix)
        if p["mbids"] and not all(map(is_uuid, p["mbids"])):
            raise errors.InvalidUUIDError("mbid" + suffix)
        self._parse_duration_and_format(p, values, suffix)
        fingerprint_string = values.get("fingerprint" + suffix)
        if not fingerprint_string:
            raise errors.MissingParameterError("fingerprint" + suffix)
        p["fingerprint"] = decode_fingerprint(fingerprint_string)
        if not p["fingerprint"]:
            logger.info("Got invalid fingerprint %r", fingerprint_string)
            raise errors.InvalidFingerprintError()
        p["bitrate"] = values.get("bitrate" + suffix, type=int) or None
        if p["bitrate"] is not None and p["bitrate"] <= 0:
            raise errors.InvalidBitrateError("bitrate" + suffix)
        p["track"] = values.get("track" + suffix)
        p["artist"] = values.get("artist" + suffix)
        p["album"] = values.get("album" + suffix)
        p["album_artist"] = values.get("albumartist" + suffix)
        p["track_no"] = values.get("trackno" + suffix, type=int)
        p["disc_no"] = values.get("discno" + suffix, type=int)
        p["year"] = values.get("year" + suffix, type=int)
        self.submissions.append(p)

    def parse(self, values, db):
        # type: (MultiDict, DatabaseContext) -> None
        super(SubmitHandlerParams, self).parse(values, db)
        self._parse_client(values, db)
        self._parse_user(values, db)
        self.wait = values.get("wait", type=int, default=0)
        self.submissions = []  # type: List[Dict[str, Any]]
        suffixes = list(iter_args_suffixes(values, "fingerprint"))
        if not suffixes:
            raise errors.MissingParameterError("fingerprint")
        for i, suffix in enumerate(suffixes):
            try:
                self._parse_submission(values, suffix)
            except errors.WebServiceError:
                if not self.submissions and i + 1 == len(suffixes):
                    raise


class SubmitHandler(APIHandler):
    params_class = SubmitHandlerParams
    meta_fields = (
        "track",
        "artist",
        "album",
        "album_artist",
        "track_no",
        "disc_no",
        "year",
    )

    def _handle_internal(self, params):
        # type: (APIHandlerParams) -> Dict[str, Any]
        assert isinstance(params, SubmitHandlerParams)

        response = {"submissions": []}  # type: Dict[str, Any]
        ids = set()  # type: Set[int]

        ingest_db = self.ctx.db.get_ingest_db()

        for p in params.submissions:
            mbids = p["mbids"] or [None]
            for mbid in mbids:
                values = {
                    "mbid": mbid or None,
                    "puid": p["puid"] or None,
                    "bitrate": p["bitrate"] or None,
                    "fingerprint": p["fingerprint"],
                    "length": p["duration"],
                    "format": p["format"] or None,
                    "account_id": params.account_id,
                    "application_id": params.application_id,
                    "application_version": params.application_version,
                }
                meta_values = dict((n, p[n]) for n in self.meta_fields if p[n])
                if any(meta_values.values()):
                    values["meta"] = meta_values
                if p["foreignid"]:
                    values["foreignid"] = p["foreignid"]
                if (
                    values.get("mbid") is None
                    and values.get("puid") is None
                    and values.get("meta") is None
                ):
                    continue
                id = insert_submission(ingest_db, values)
                ids.add(id)
                submission = {"id": id, "status": "pending"}
                if p["index"]:
                    submission["index"] = p["index"]
                response["submissions"].append(submission)

        self.ctx.db.session.flush()
        self.ctx.db.session.commit()

        if self.ctx.statsd is not None:
            self.ctx.statsd.incr("new_submissions", len(ids))

        return response
