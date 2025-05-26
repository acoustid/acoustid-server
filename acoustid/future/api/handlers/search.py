import msgspec
from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import Response

from ..utils import MsgspecResponse


class SearchRequest(msgspec.Struct):
    pass


class SearchResponse(msgspec.Struct):
    pass


@requires(["app"])
async def handle_search(request: Request) -> Response:
    body = await request.body()
    req = msgspec.json.decode(body, type=SearchRequest)

    _ = req

    response = SearchResponse()
    return MsgspecResponse(response)
