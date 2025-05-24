from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route


def handle_health(request: Request) -> Response:
    return Response(content="OK", media_type="text/plain")


def handle_get_fingerprint(request: Request) -> Response:
    fingerprint_id = request.path_params["id"]
    return Response(content=fingerprint_id, media_type="text/plain")


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/v2/fingerprint/{id}", handle_get_fingerprint, methods=["GET"]),
            Route("/health", handle_health, methods=["GET"]),
        ],
    )
