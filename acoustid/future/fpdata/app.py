from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route


def handle_health(request: Request) -> Response:
    return Response(content="OK", media_type="text/plain")


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/health", handle_health, methods=["GET"]),
        ],
    )
