from msgspec import ValidationError
from starlette.applications import Starlette
from starlette.authentication import AuthCredentials, BaseUser
from starlette.middleware import Middleware
from starlette.middleware.authentication import (
    AuthenticationBackend,
    AuthenticationMiddleware,
)
from starlette.requests import HTTPConnection
from starlette.routing import Route

from ..apiutils import on_auth_error, on_validation_error
from .handlers.monitoring import handle_health
from .handlers.submit import handle_submit


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


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/v3/submit", handle_submit, methods=["POST"]),
            Route("/health", handle_health, methods=["GET"]),
        ],
        middleware=[
            Middleware(
                AuthenticationMiddleware,
                backend=ApiAuthBackend(),
                on_error=on_auth_error,
            ),
        ],
        exception_handlers={
            ValidationError: on_validation_error,
        },
    )
