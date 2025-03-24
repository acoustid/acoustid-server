import msgspec
from starlette.responses import Response


class MsgspecResponse(Response):
    media_type = "application/json"

    def render(self, content: msgspec.Struct) -> bytes:
        return msgspec.json.encode(content)


class ErrorResponse(msgspec.Struct):
    error: str
