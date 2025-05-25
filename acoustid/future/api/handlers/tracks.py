import uuid
from typing import cast

import msgspec
from starlette.requests import Request
from starlette.responses import Response

from acoustid.future.data.db import FingerprintDB
from acoustid.future.data.tracks import list_tracks_by_mbid

from ..utils import MsgspecResponse, get_ctx


class ListByMBIDRequest(msgspec.Struct):
    mbid: uuid.UUID


class ListByFingerprintRequest(msgspec.Struct):
    id: uuid.UUID


class TrackInfo(msgspec.Struct):
    id: uuid.UUID
    disabled: bool | None = None


class ListResponse(msgspec.Struct):
    tracks: list[TrackInfo]


async def handle_list_tracks_by_mbid(request: Request) -> Response:
    ctx = get_ctx(request)

    params = dict(request.query_params)
    req = msgspec.convert(params, type=ListByMBIDRequest)

    tracks = []

    async with ctx.app_context.get_fingerprint_db().connect() as db:
        fp_db = cast(FingerprintDB, db)
        for track in await list_tracks_by_mbid(fp_db, req.mbid):
            tracks.append(TrackInfo(id=track["gid"], disabled=track["disabled"]))

    return MsgspecResponse(ListResponse(tracks=tracks))


async def handle_list_tracks_by_fingerprint(request: Request) -> Response:
    ctx = get_ctx(request)

    params = dict(request.query_params)
    req = msgspec.convert(params, type=ListByFingerprintRequest)

    _ = ctx
    _ = req

    return MsgspecResponse(ListResponse(tracks=[]))
