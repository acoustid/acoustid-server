import asyncio
import uuid

import msgspec
from acoustid_ext.fingerprint import (
    FingerprintError,
    compute_simhash,
    decode_legacy_fingerprint,
)
from msgspec import ValidationError
from starlette.requests import Request
from starlette.responses import Response

from ..utils import MsgspecResponse


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


class SubmissionStatus(msgspec.Struct):
    submission_id: int = msgspec.field(name="id")
    status: str


class SubmissionRequest(msgspec.Struct):
    submissions: list[Submission]


class SubmissionResponse(msgspec.Struct):
    submissions: list[SubmissionStatus] = msgspec.field(default_factory=list)


ALLOWED_FINGERPRINT_VERSIONS = frozenset({1})


async def handle_submit(request: Request) -> Response:
    body = await request.body()
    req = msgspec.json.decode(body, type=SubmissionRequest)

    response = SubmissionResponse()

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
        response.submissions.append(SubmissionStatus(submission_id=1, status="pending"))

    return MsgspecResponse(response)
