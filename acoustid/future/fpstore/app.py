import msgspec
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from ..apiutils import default_exception_handlers


def handle_health(request: Request) -> Response:
    return Response(content="OK", media_type="text/plain")


class GetFingerprintRequest(msgspec.Struct):
    fingerprint_id: int


async def handle_get_fingerprint(request: Request) -> Response:
    raw_body = await request.body()
    body = msgspec.json.decode(raw_body, type=GetFingerprintRequest)
    fingerprint_id = body.fingerprint_id
    return Response(content=str(fingerprint_id), media_type="text/plain")


async def handle_search(request: Request) -> Response:
    return Response(content="OK", media_type="text/plain")


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/v2/fingerprint/_get", handle_get_fingerprint, methods=["POST"]),
            Route("/v2/fingerprint/_search", handle_search, methods=["POST"]),
            Route("/health", handle_health, methods=["GET"]),
        ],
        exception_handlers=default_exception_handlers,
    )
