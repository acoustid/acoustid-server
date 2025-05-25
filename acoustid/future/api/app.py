import functools
import logging
import os
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator, TypedDict

import sqlalchemy
from msgspec import ValidationError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from starlette.applications import Starlette
from starlette.authentication import AuthCredentials, BaseUser
from starlette.middleware import Middleware
from starlette.middleware.authentication import (
    AuthenticationBackend,
    AuthenticationMiddleware,
)
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import HTTPConnection, Request
from starlette.responses import Response
from starlette.routing import Route

from acoustid.config import Config

from .handlers.monitoring import handle_health
from .handlers.submit import handle_submit
from .handlers.tracks import (
    handle_list_tracks_by_fingerprint,
    handle_list_tracks_by_mbid,
)
from .utils import on_auth_error, on_validation_error

logger = logging.getLogger(__name__)


class ApiUser(BaseUser):

    def __init__(self, app_id: int, user_id: int | None):
        self.app_id = app_id
        self.user_id = user_id

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def display_name(self) -> str:
        return ""

    @property
    def identity(self) -> str:
        return f"app:{self.app_id} user:{self.user_id}"


class ApiAuthBackend(AuthenticationBackend):
    async def authenticate(
        self, conn: HTTPConnection
    ) -> tuple[AuthCredentials, BaseUser] | None:
        app_key = conn.headers.get("X-App-Key")
        user_key = conn.headers.get("X-User-Key")

        if not app_key:
            return None

        app_id = 1
        user_id = 1 if user_key else None

        return AuthCredentials(["app", "user"]), ApiUser(app_id, user_id)


class AppContext:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.database_engines = config.databases.create_async_engines()

    async def get_fingerprint_db(self) -> AsyncEngine:
        return self.database_engines["fingerprint"]

    async def get_app_db(self) -> AsyncEngine:
        return self.database_engines["app"]

    async def get_ingest_db(self) -> AsyncEngine:
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
            request.state.ctx = request_ctx
            response = await call_next(request)
            return response


@asynccontextmanager
async def app_lifespan(config: Config, app: Starlette):
    async with AppContext(config) as app_ctx:
        app.state.app_ctx = app_ctx
        yield


def create_app(config_file: str | None = None, tests: bool = False) -> Starlette:
    config = Config.load(config_file, tests=tests)
    _ = config

    return Starlette(
        routes=[
            Route("/v3/submit", handle_submit, methods=["POST"]),
            Route(
                "/v3/track/list_by_mbid", handle_list_tracks_by_mbid, methods=["GET"]
            ),
            Route(
                "/v3/track/list_by_fingerprint",
                handle_list_tracks_by_fingerprint,
                methods=["GET"],
            ),
            Route("/health", handle_health, methods=["GET"]),
        ],
        middleware=[
            Middleware(
                RequestContextMiddleware,
            ),
            Middleware(
                AuthenticationMiddleware,
                backend=ApiAuthBackend(),
                on_error=on_auth_error,
            ),
        ],
        exception_handlers={
            ValidationError: on_validation_error,
        },
        lifespan=functools.partial(app_lifespan, config),
    )
