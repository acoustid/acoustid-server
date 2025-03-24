import msgspec
from starlette.requests import Request
from starlette.responses import Response


class MsgspecResponse(Response):
    media_type = "application/json"

    def render(self, content: msgspec.Struct) -> bytes:
        return msgspec.json.encode(content)


class ErrorResponse(msgspec.Struct):
    error: str


def on_validation_error(_: Request, exc: Exception) -> Response:
    return MsgspecResponse(status_code=400, content=ErrorResponse(error=str(exc)))


def on_auth_error(_: Request, exc: Exception) -> Response:
    return MsgspecResponse(status_code=401, content=ErrorResponse(error=str(exc)))
