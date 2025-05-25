import uuid

import msgspec
from starlette.requests import Request
from starlette.responses import Response


class ListByMBIDRequest(msgspec.Struct):
    mbid: uuid.UUID


class ListByMBIDResponse(msgspec.Struct):
    pass


async def handle_list_by_mbid(request: Request) -> Response:
    raise NotImplementedError()
