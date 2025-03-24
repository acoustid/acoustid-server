from msgspec import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .handlers.monitoring import handle_health
from .handlers.submit import handle_submit
from .utils import ErrorResponse, MsgspecResponse


async def handle_validation_error(request: Request, exc: Exception) -> Response:
    return MsgspecResponse(status_code=400, content=ErrorResponse(error=str(exc)))


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/v3/submit", handle_submit, methods=["POST"]),
            Route("/health", handle_health, methods=["GET"]),
        ],
        exception_handlers={
            ValidationError: handle_validation_error,
        },
    )
