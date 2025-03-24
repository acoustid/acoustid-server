import asyncio
import uuid

import msgspec
from acoustid_ext.fingerprint import (
    FingerprintError,
    compute_simhash,
    decode_legacy_fingerprint,
)
from msgspec import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from .handlers.monitoring import handle_health


class MsgspecResponse(Response):
    media_type = "application/json"

    def render(self, content: msgspec.Struct) -> bytes:
        return msgspec.json.encode(content)


class ErrorResponse(msgspec.Struct):
    error: str


class Metadata(msgspec.Struct):
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    album_artist: str | None = None
    track_no: int | None = None
    disc_no: int | None = None
    year: int | None = None


class Submission(msgspec.Struct):
    fingerprint: str
    duration: float
    mbid: uuid.UUID | None = None
    metadata: Metadata | None = None


class SubmissionRequest(msgspec.Struct):
    submissions: list[Submission]


class SubmissionResponse(msgspec.Struct):
    submission_id: int


ALLOWED_FINGERPRINT_VERSIONS = frozenset({1})


async def handle_submission(request: Request) -> MsgspecResponse:
    body = await request.body()
    req = msgspec.json.decode(body, type=SubmissionRequest)

    for submission in req.submissions:
        try:
            fp = await asyncio.to_thread(
                decode_legacy_fingerprint,
                submission.fingerprint,
            )
        except FingerprintError as e:
            raise ValidationError("Invalid fingerprint") from e

        if fp.version not in ALLOWED_FINGERPRINT_VERSIONS:
            raise ValidationError("Unsupported fingerprint version")

        if len(fp.hashes) < 10:
            raise ValidationError("Fingerprint too short")

        print(compute_simhash(fp.hashes))
        print(fp)

    return MsgspecResponse(content=SubmissionResponse(submission_id=1))


async def handle_validation_error(request: Request, exc: Exception) -> MsgspecResponse:
    return MsgspecResponse(status_code=400, content=ErrorResponse(error=str(exc)))


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/v3/submission", handle_submission, methods=["POST"]),
            Route("/health", handle_health, methods=["GET"]),
        ],
        exception_handlers={
            ValidationError: handle_validation_error,
        },
    )
