import uuid

import msgspec
from starlette.requests import Request
from starlette.responses import Response

from ..utils import MsgspecResponse


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
    params = dict(request.query_params)
    req = msgspec.convert(params, type=ListByMBIDRequest)
    _ = req
    return MsgspecResponse(ListResponse(tracks=[]))


async def handle_list_tracks_by_fingerprint(request: Request) -> Response:
    params = dict(request.query_params)
    req = msgspec.convert(params, type=ListByMBIDRequest)
    _ = req
    return MsgspecResponse(ListResponse(tracks=[]))
