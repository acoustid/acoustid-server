import uuid
import msgspec
from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import Response

from ..utils import MsgspecResponse


class SearchRequest(msgspec.Struct):
    pass


class Metadata(msgspec.Struct):
    id: uuid.UUID
    sources: int


class Result(msgspec.Struct):
    id: uuid.UUID
    score: float
    sources: int
    metadata: list[Metadata]


class SearchResponse(msgspec.Struct):
    results: list[Result]


@requires(["app"])
async def handle_search(request: Request) -> Response:
    body = await request.body()
    req = msgspec.json.decode(body, type=SearchRequest)

    _ = req

    response = SearchResponse(results=[])
    return MsgspecResponse(response)
