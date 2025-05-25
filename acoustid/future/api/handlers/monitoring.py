import msgspec
from starlette.requests import Request
from starlette.responses import Response

from ..utils import MsgspecResponse


class Health(msgspec.Struct):
    ready: bool


def handle_health(request: Request) -> Response:
    return MsgspecResponse(Health(ready=True))
