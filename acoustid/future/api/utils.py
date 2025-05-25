from contextlib import AsyncExitStack

import msgspec
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from acoustid.config import Config


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


class AppContext:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.database_engines = config.databases.create_async_engines()

    def get_fingerprint_db(self) -> AsyncEngine:
        return self.database_engines["fingerprint"]

    def get_app_db(self) -> AsyncEngine:
        return self.database_engines["app"]

    def get_ingest_db(self) -> AsyncEngine:
        return self.database_engines["ingest"]

    async def aclose(self) -> None:
        for engine in self.database_engines.values():
            await engine.dispose()

    async def __aenter__(self) -> "AppContext":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()


class RequestContext:
    def __init__(self, app_context: AppContext) -> None:
        self.app_context = app_context
        self.cleanup = AsyncExitStack()

    async def __aenter__(self) -> "RequestContext":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.cleanup.aclose()


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        async with RequestContext(request.app.state.app_ctx) as request_ctx:
            set_ctx(request, request_ctx)
            response = await call_next(request)
            return response


def set_ctx(request: Request, ctx: RequestContext) -> None:
    request.state.ctx = ctx


def get_ctx(request: Request) -> RequestContext:
    return request.state.ctx
