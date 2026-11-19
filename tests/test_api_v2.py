# Copyright (C) 2011,2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import json
import unittest
from datetime import date
from typing import Any, Dict, Optional
from unittest import mock
from uuid import UUID

import pytest
from sqlalchemy import sql
from werkzeug.datastructures import MultiDict
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from acoustid import const
from acoustid import tables
from acoustid import tables as schema
from acoustid.api import errors
from acoustid.api.v2 import (
    APIHandler,
    APIHandlerParams,
    FingerprintLookupQuery,
    LookupHandler,
    LookupHandlerParams,
    SubmitHandler,
    SubmitHandlerParams,
    app_user_key_policy_cache,
)
from acoustid.api.v2.internal import (
    CreateApplicationHandler,
    CreateApplicationHandlerParams,
    UpdateApplicationStatusHandler,
    UpdateApplicationStatusHandlerParams,
)
from acoustid.api.v2.misc import UserCreateAnonymousHandler, UserLookupHandler
from acoustid.script import ScriptContext
from tests import (
    TEST_1_FP,
    TEST_1_FP_RAW,
    TEST_1_LENGTH,
    TEST_2_FP,
    TEST_2_FP_RAW,
    TEST_2_LENGTH,
    assert_json_equals,
    assert_raises,
    prepare_database,
    with_script_context,
)


@with_script_context
def test_ok(ctx):
    # type: (ScriptContext) -> None
    handler = APIHandler(ctx)
    resp = handler._ok({"tracks": [{"id": 1, "name": "Track 1"}]}, "json")
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {"status": "ok", "tracks": [{"id": 1, "name": "Track 1"}]}
    assert_json_equals(expected, resp.data)
    assert "200 OK" == resp.status


@with_script_context
def test_error(ctx):
    # type: (ScriptContext) -> None
    handler = APIHandler(ctx)
    resp = handler._error(123, "something is wrong", "json")
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {
        "status": "error",
        "error": {"message": "something is wrong", "code": 123},
    }
    assert_json_equals(expected, resp.data)
    assert "400 BAD REQUEST" == resp.status
    resp = handler._error(234, "oops", "json", status=500)
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {"status": "error", "error": {"message": "oops", "code": 234}}
    assert_json_equals(expected, resp.data)
    assert "500 INTERNAL SERVER ERROR" == resp.status


@with_script_context
def test_api_handler_params_jsonp(ctx):
    # type: (ScriptContext) -> None
    values = MultiDict({"client": "app1key", "format": "jsonp"})  # type: MultiDict
    params = APIHandlerParams(ctx.config)
    params.parse(values, ctx)
    assert "jsonp:jsonAcoustidApi" == params.format
    values = MultiDict({"client": "app1key", "format": "jsonp", "jsoncallback": "$foo"})
    params = APIHandlerParams(ctx.config)
    params.parse(values, ctx)
    assert "jsonp:$foo" == params.format
    values = MultiDict({"client": "app1key", "format": "jsonp", "jsoncallback": "///"})
    params = APIHandlerParams(ctx.config)
    params.parse(values, ctx)
    assert "jsonp:jsonAcoustidApi" == params.format


@with_script_context
def test_lookup_handler_params(ctx):
    # type: (ScriptContext) -> None
    # invalid format
    values = MultiDict({"format": "xls"})  # type: MultiDict
    params = LookupHandlerParams(ctx.config)
    assert_raises(errors.UnknownFormatError, params.parse, values, ctx.db)
    # missing client
    values = MultiDict({"format": "json"})
    params = LookupHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # invalid client
    values = MultiDict({"format": "json", "client": "N/A"})
    params = LookupHandlerParams(ctx.config)
    assert_raises(errors.InvalidAPIKeyError, params.parse, values, ctx.db)
    # missing duration
    values = MultiDict({"format": "json", "client": "app1key"})
    params = LookupHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # missing fingerprint
    values = MultiDict(
        {"format": "json", "client": "app1key", "duration": str(TEST_1_LENGTH)}
    )
    params = LookupHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # invalid fingerprint
    values = MultiDict(
        {
            "format": "json",
            "client": "app1key",
            "duration": str(TEST_1_LENGTH),
            "fingerprint": "...",
        }
    )
    params = LookupHandlerParams(ctx.config)
    assert_raises(errors.InvalidFingerprintError, params.parse, values, ctx.db)
    # all ok
    values = MultiDict(
        {
            "format": "json",
            "client": "app1key",
            "duration": str(TEST_1_LENGTH),
            "fingerprint": TEST_1_FP,
        }
    )
    params = LookupHandlerParams(ctx.config)
    params.parse(values, ctx.db)
    assert "json" == params.format
    assert 1 == params.application_id
    assert len(params.fingerprints) == 1
    assert isinstance(params.fingerprints[0], FingerprintLookupQuery)
    assert TEST_1_LENGTH == params.fingerprints[0].duration
    assert TEST_1_FP_RAW == params.fingerprints[0].fingerprint


class WebServiceErrorHandler(APIHandler):
    params_class = APIHandlerParams

    def _handle_internal(self, params):
        raise errors.InvalidAPIKeyError()


class InternalErrorHandler(APIHandler):
    params_class = APIHandlerParams

    def _handle_internal(self, params):
        return {"infinity": 43 / 0}


@with_script_context
def test_apihandler_ws_error_400(ctx):
    # type: (ScriptContext) -> None
    values = {"format": "json"}
    builder = EnvironBuilder(method="POST", data=values)
    handler = WebServiceErrorHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {
        "status": "error",
        "error": {
            "message": "invalid API key",
            "code": 4,
        },
    }
    assert_json_equals(expected, resp.data)
    assert "400 BAD REQUEST" == resp.status


@with_script_context
def test_apihandler_ws_error_500(ctx):
    # type: (ScriptContext) -> None
    values = {"format": "json"}
    builder = EnvironBuilder(method="POST", data=values)
    handler = InternalErrorHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {
        "status": "error",
        "error": {
            "message": "internal error",
            "code": 5,
        },
    }
    assert_json_equals(expected, resp.data)
    assert "500 INTERNAL SERVER ERROR" == resp.status


@with_script_context
def test_lookup_handler(ctx: ScriptContext) -> None:
    from mbdata.sample_data import create_sample_data
    from sqlalchemy.orm import Session

    create_sample_data(Session(ctx.db.get_fingerprint_db()))
    ctx.db.session.commit()

    values = {
        "format": "json",
        "client": "app1key",
        "duration": str(TEST_1_LENGTH),
        "fingerprint": TEST_1_FP,
    }
    builder = EnvironBuilder(method="POST", data=values)

    # no matches
    handler = LookupHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {"status": "ok", "results": []}  # type: Dict[str, Any]
    assert_json_equals(expected, resp.data)
    assert "200 OK" == resp.status

    # one exact match
    prepare_database(
        ctx.db.get_fingerprint_db(),
        """
INSERT INTO fingerprint (length, fingerprint, track_id, submission_count)
    VALUES (:length, :fp, 1, 1);
""",
        {"length": TEST_1_LENGTH, "fp": TEST_1_FP_RAW},
    )
    ctx.db.session.commit()

    handler = LookupHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {
        "status": "ok",
        "results": [
            {
                "id": "eb31d1c3-950e-468b-9e36-e46fa75b1291",
                "score": 1.0,
            }
        ],
    }
    assert_json_equals(expected, resp.data)
    assert "200 OK" == resp.status

    # one exact match with MBIDs
    values = {
        "format": "json",
        "client": "app1key",
        "duration": str(TEST_1_LENGTH),
        "fingerprint": TEST_1_FP,
        "meta": "1",
    }
    builder = EnvironBuilder(method="POST", data=values)
    handler = LookupHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {
        "status": "ok",
        "results": [
            {
                "id": "eb31d1c3-950e-468b-9e36-e46fa75b1291",
                "score": 1.0,
                "recordings": [{"id": "b81f83ee-4da4-11e0-9ed8-0025225356f3"}],
            }
        ],
    }
    assert_json_equals(expected, resp.data)
    assert "200 OK" == resp.status

    # one exact match with MBIDs and metadata
    prepare_database(
        ctx.db.get_fingerprint_db(),
        "INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (1, '7853bd8c-2141-4b4d-9f62-578bab214ab9', 1)",
    )
    ctx.db.session.commit()
    values = {
        "format": "json",
        "client": "app1key",
        "duration": str(TEST_1_LENGTH),
        "fingerprint": TEST_1_FP,
        "meta": "2",
    }
    builder = EnvironBuilder(method="POST", data=values)
    handler = LookupHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {
        "status": "ok",
        "results": [
            {
                "id": "eb31d1c3-950e-468b-9e36-e46fa75b1291",
                "score": 1.0,
                "recordings": [
                    {
                        "id": "7853bd8c-2141-4b4d-9f62-578bab214ab9",
                        "duration": 367.0,
                        "tracks": [
                            {
                                "title": "Moon",
                                "duration": 367.0,
                                "artists": [
                                    {
                                        "id": "6edc70bb-c340-4ae6-bdd4-d5fb0c7411de",
                                        "name": "Alva Noto & Ryuichi Sakamoto",
                                    }
                                ],
                                "position": 5,
                                "medium": {
                                    "track_count": 16,
                                    "position": 1,
                                    "release": {
                                        "id": "7643ee96-fe19-4b76-aa9a-e8af7d0e9d73",
                                        "title": "XVI Reflections on Classical Music",
                                    },
                                    "format": "CD",
                                },
                            }
                        ],
                    },
                    {"id": "b81f83ee-4da4-11e0-9ed8-0025225356f3"},
                ],
            }
        ],
    }
    assert_json_equals(expected, resp.data)
    assert "200 OK" == resp.status

    # duplicate fingerprint
    prepare_database(
        ctx.db.get_fingerprint_db(),
        """
INSERT INTO fingerprint (length, fingerprint, track_id, submission_count)
    VALUES (:length, :fingerprint, 1, 1);
""",
        {"length": TEST_1_LENGTH, "fingerprint": TEST_1_FP_RAW},
    )
    ctx.db.session.commit()

    values = {
        "format": "json",
        "client": "app1key",
        "duration": str(TEST_1_LENGTH),
        "fingerprint": TEST_1_FP,
    }
    builder = EnvironBuilder(method="POST", data=values)
    handler = LookupHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {
        "status": "ok",
        "results": [
            {
                "id": "eb31d1c3-950e-468b-9e36-e46fa75b1291",
                "score": 1.0,
            }
        ],
    }
    assert_json_equals(expected, resp.data)
    assert "200 OK" == resp.status


@with_script_context
def test_submit_handler_params(ctx):
    # type: (ScriptContext) -> None
    # invalid format
    values = MultiDict({"format": "xls"})  # type: MultiDict
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.UnknownFormatError, params.parse, values, ctx.db)
    # missing client
    values = MultiDict({"format": "json"})
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # invalid client
    values = MultiDict({"format": "json", "client": "N/A"})
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.InvalidAPIKeyError, params.parse, values, ctx.db)
    # missing user
    values = MultiDict({"format": "json", "client": "app1key"})
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # invalid user
    values = MultiDict({"format": "json", "client": "app1key", "user": "N/A"})
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.InvalidUserAPIKeyError, params.parse, values, ctx.db)
    # missing fingerprint
    values = MultiDict({"format": "json", "client": "app1key", "user": "user1key"})
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # wrong foreign id
    values = MultiDict(
        {
            "format": "json",
            "client": "app1key",
            "user": "user1key",
            "foreignid": "aaa",
            "duration": str(TEST_1_LENGTH),
            "fingerprint": TEST_1_FP,
            "bitrate": "192",
            "fileformat": "MP3",
        }
    )
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.InvalidForeignIDError, params.parse, values, ctx.db)
    # wrong mbid
    values = MultiDict(
        {
            "format": "json",
            "client": "app1key",
            "user": "user1key",
            "mbid": "4d814cb1-20ec-494f-996f-xxxxxxxxxxxx",
            "duration": str(TEST_1_LENGTH),
            "fingerprint": TEST_1_FP,
            "bitrate": "192",
            "fileformat": "MP3",
        }
    )
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.InvalidUUIDError, params.parse, values, ctx.db)
    # one wrong mbid, one good
    values = MultiDict(
        {
            "format": "json",
            "client": "app1key",
            "user": "user1key",
            "mbid": [
                "4d814cb1-20ec-494f-996f-xxxxxxxxxxxx",
                "66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea",
            ],
            "duration": str(TEST_1_LENGTH),
            "fingerprint": TEST_1_FP,
            "bitrate": "192",
            "fileformat": "MP3",
        }
    )
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.InvalidUUIDError, params.parse, values, ctx.db)
    # wrong puid
    values = MultiDict(
        {
            "format": "json",
            "client": "app1key",
            "user": "user1key",
            "puid": "4d814cb1-20ec-494f-996f-xxxxxxxxxxxx",
            "duration": str(TEST_1_LENGTH),
            "fingerprint": TEST_1_FP,
            "bitrate": "192",
            "fileformat": "MP3",
        }
    )
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.InvalidUUIDError, params.parse, values, ctx.db)
    # empty fingerprint
    values = MultiDict(
        {
            "format": "json",
            "client": "app1key",
            "user": "user1key",
            "mbid": [
                "4d814cb1-20ec-494f-996f-f31ca8a49784",
                "66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea",
            ],
            "puid": "4e823498-c77d-4bfb-b6cc-85b05c2783cf",
            "duration": str(TEST_1_LENGTH),
            "fingerprint": "",
            "bitrate": "192",
            "fileformat": "MP3",
        }
    )
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # missing duration
    values = MultiDict(
        {
            "format": "json",
            "client": "app1key",
            "user": "user1key",
            "mbid": [
                "4d814cb1-20ec-494f-996f-f31ca8a49784",
                "66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea",
            ],
            "puid": "4e823498-c77d-4bfb-b6cc-85b05c2783cf",
            "fingerprint": TEST_1_FP,
            "bitrate": "192",
            "fileformat": "MP3",
        }
    )
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # all ok (single submission)
    values = MultiDict(
        {
            "format": "json",
            "client": "app1key",
            "user": "user1key",
            "mbid": [
                "4d814cb1-20ec-494f-996f-f31ca8a49784",
                "66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea",
            ],
            "puid": "4e823498-c77d-4bfb-b6cc-85b05c2783cf",
            "foreignid": "foo:123",
            "duration": str(TEST_1_LENGTH),
            "fingerprint": TEST_1_FP,
            "bitrate": "192",
            "fileformat": "MP3",
        }
    )
    params = SubmitHandlerParams(ctx.config)
    params.parse(values, ctx.db)
    assert 1 == len(params.submissions)
    assert [
        "4d814cb1-20ec-494f-996f-f31ca8a49784",
        "66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea",
    ] == params.submissions[0]["mbids"]
    assert "4e823498-c77d-4bfb-b6cc-85b05c2783cf" == params.submissions[0]["puid"]
    assert "foo:123" == params.submissions[0]["foreignid"]
    assert TEST_1_LENGTH == params.submissions[0]["duration"]
    assert TEST_1_FP_RAW == params.submissions[0]["fingerprint"]
    assert 192 == params.submissions[0]["bitrate"]
    assert "MP3" == params.submissions[0]["format"]
    # all ok (multiple submissions)
    values = MultiDict(
        {
            "format": "json",
            "client": "app1key",
            "user": "user1key",
            "mbid.0": "4d814cb1-20ec-494f-996f-f31ca8a49784",
            "puid.0": "4e823498-c77d-4bfb-b6cc-85b05c2783cf",
            "duration.0": str(TEST_1_LENGTH),
            "fingerprint.0": TEST_1_FP,
            "bitrate.0": "192",
            "fileformat.0": "MP3",
            "mbid.1": "66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea",
            "puid.1": "57b202a3-242b-4896-a79c-cac34bbca0b6",
            "duration.1": str(TEST_2_LENGTH),
            "fingerprint.1": TEST_2_FP,
            "bitrate.1": "500",
            "fileformat.1": "FLAC",
        }
    )
    params = SubmitHandlerParams(ctx.config)
    params.parse(values, ctx.db)
    assert 2 == len(params.submissions)
    assert ["4d814cb1-20ec-494f-996f-f31ca8a49784"] == params.submissions[0]["mbids"]
    assert "4e823498-c77d-4bfb-b6cc-85b05c2783cf" == params.submissions[0]["puid"]
    assert TEST_1_LENGTH == params.submissions[0]["duration"]
    assert TEST_1_FP_RAW == params.submissions[0]["fingerprint"]
    assert 192 == params.submissions[0]["bitrate"]
    assert "MP3" == params.submissions[0]["format"]
    assert ["66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea"] == params.submissions[1]["mbids"]
    assert "57b202a3-242b-4896-a79c-cac34bbca0b6" == params.submissions[1]["puid"]
    assert TEST_2_LENGTH == params.submissions[1]["duration"]
    assert TEST_2_FP_RAW == params.submissions[1]["fingerprint"]
    assert 500 == params.submissions[1]["bitrate"]
    assert "FLAC" == params.submissions[1]["format"]
    # one incorrect, one correct
    values = MultiDict(
        {
            "format": "json",
            "client": "app1key",
            "user": "user1key",
            "mbid.0": "4d814cb1-20ec-494f-996f-f31ca8a49784",
            "puid.0": "4e823498-c77d-4bfb-b6cc-85b05c2783cf",
            "duration.0": str(TEST_1_LENGTH),
            "fingerprint.0": TEST_1_FP,
            "bitrate.0": "192",
            "fileformat.0": "MP3",
            "mbid.1": "66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea",
            "puid.1": "57b202a3-242b-4896-a79c-cac34bbca0b6",
            "duration.1": str(TEST_2_LENGTH),
            "fingerprint.1": "",
            "bitrate.1": "500",
            "fileformat.1": "FLAC",
        }
    )
    params = SubmitHandlerParams(ctx.config)
    params.parse(values, ctx.db)
    assert 1 == len(params.submissions)
    assert ["4d814cb1-20ec-494f-996f-f31ca8a49784"] == params.submissions[0]["mbids"]
    assert "4e823498-c77d-4bfb-b6cc-85b05c2783cf" == params.submissions[0]["puid"]
    assert TEST_1_LENGTH == params.submissions[0]["duration"]
    assert TEST_1_FP_RAW == params.submissions[0]["fingerprint"]
    assert 192 == params.submissions[0]["bitrate"]
    assert "MP3" == params.submissions[0]["format"]


@with_script_context
def test_submit_handler(ctx):
    # type: (ScriptContext) -> None
    values = {
        "format": "json",
        "client": "app1key",
        "user": "user1key",
        "duration": str(TEST_1_LENGTH),
        "fingerprint": TEST_1_FP,
        "bitrate": 192,
        "mbid": "b9c05616-1874-4d5d-b30e-6b959c922d28",
        "fileformat": "FLAC",
    }
    builder = EnvironBuilder(method="POST", data=values)
    handler = SubmitHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {"status": "ok", "submissions": [{"status": "pending", "id": 1}]}
    assert_json_equals(expected, resp.data)
    assert "200 OK" == resp.status
    query = tables.submission.select().order_by(tables.submission.c.id.desc()).limit(1)
    submission = ctx.db.get_ingest_db().execute(query).one()._mapping
    assert UUID("b9c05616-1874-4d5d-b30e-6b959c922d28") == submission["mbid"]
    assert "FLAC" == submission["format"]
    assert 192 == submission["bitrate"]
    assert TEST_1_FP_RAW == submission["fingerprint"]
    assert TEST_1_LENGTH == submission["length"]


@with_script_context
def test_submit_handler_with_meta(ctx):
    # type: (ScriptContext) -> None
    values = {
        "format": "json",
        "client": "app1key",
        "user": "user1key",
        "duration": str(TEST_1_LENGTH),
        "fingerprint": TEST_1_FP,
        "bitrate": 192,
        "mbid": "b9c05616-1874-4d5d-b30e-6b959c922d28",
        "fileformat": "FLAC",
        "track": "Voodoo People",
        "artist": "The Prodigy",
        "album": "Music For The Jitled People",
        "albumartist": "Prodigy",
        "trackno": "2",
        "discno": "3",
        "year": "2030",
    }
    builder = EnvironBuilder(method="POST", data=values)
    handler = SubmitHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {"status": "ok", "submissions": [{"status": "pending", "id": 1}]}
    assert_json_equals(expected, resp.data)
    assert "200 OK" == resp.status
    query = tables.submission.select().order_by(tables.submission.c.id.desc()).limit(1)
    submission = ctx.db.get_ingest_db().execute(query).one()._mapping
    assert UUID("b9c05616-1874-4d5d-b30e-6b959c922d28") == submission["mbid"]
    assert submission["meta_id"] is None
    expected_meta = {
        "track": "Voodoo People",
        "artist": "The Prodigy",
        "album": "Music For The Jitled People",
        "album_artist": "Prodigy",
        "track_no": 2,
        "disc_no": 3,
        "year": 2030,
    }
    assert expected_meta == submission["meta"]


@with_script_context
def test_submit_handler_puid(ctx):
    # type: (ScriptContext) -> None
    values = {
        "format": "json",
        "client": "app1key",
        "user": "user1key",
        "duration": str(TEST_1_LENGTH),
        "fingerprint": TEST_1_FP,
        "bitrate": 192,
        "puid": "b9c05616-1874-4d5d-b30e-6b959c922d28",
        "fileformat": "FLAC",
    }
    builder = EnvironBuilder(method="POST", data=values)
    handler = SubmitHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {"status": "ok", "submissions": [{"status": "pending", "id": 1}]}
    assert_json_equals(expected, resp.data)
    assert "200 OK" == resp.status
    query = tables.submission.select().order_by(tables.submission.c.id.desc()).limit(1)
    submission = ctx.db.get_ingest_db().execute(query).one()._mapping
    assert submission["mbid"] is None
    assert UUID("b9c05616-1874-4d5d-b30e-6b959c922d28") == submission["puid"]
    assert "FLAC" == submission["format"]
    assert 192 == submission["bitrate"]
    assert TEST_1_FP_RAW == submission["fingerprint"]
    assert TEST_1_LENGTH == submission["length"]


@with_script_context
def test_submit_handler_foreignid(ctx):
    # type: (ScriptContext) -> None
    values = {
        "format": "json",
        "client": "app1key",
        "user": "user1key",
        "duration": str(TEST_1_LENGTH),
        "fingerprint": TEST_1_FP,
        "bitrate": 192,
        "foreignid": "foo:123",
        "track": "Voodoo People",
        "fileformat": "FLAC",
    }
    builder = EnvironBuilder(method="POST", data=values)
    handler = SubmitHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {"status": "ok", "submissions": [{"status": "pending", "id": 1}]}
    assert_json_equals(expected, resp.data)
    assert "200 OK" == resp.status
    query = tables.submission.select().order_by(tables.submission.c.id.desc()).limit(1)
    submission = ctx.db.get_ingest_db().execute(query).one()._mapping
    assert submission["mbid"] is None
    assert submission["puid"] is None
    assert "foo:123" == submission["foreignid"]
    assert "FLAC" == submission["format"]
    assert 192 == submission["bitrate"]
    assert TEST_1_FP_RAW == submission["fingerprint"]
    assert TEST_1_LENGTH == submission["length"]


@with_script_context
def test_user_create_anonumous_handler(ctx):
    # type: (ScriptContext) -> None
    values = {"format": "json", "client": "app1key"}
    builder = EnvironBuilder(method="POST", data=values)
    handler = UserCreateAnonymousHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    assert "200 OK" == resp.status
    data = json.loads(resp.data)
    assert "ok" == data["status"]
    query = tables.account.select().where(
        tables.account.c.apikey == data["user"]["apikey"]
    )
    user = ctx.db.get_app_db().execute(query).one()._mapping
    assert user


@with_script_context
def test_user_lookup_handler(ctx):
    # type: (ScriptContext) -> None
    values = {"format": "json", "client": "app1key", "user": "user1key"}
    builder = EnvironBuilder(method="POST", data=values)
    handler = UserLookupHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    assert "200 OK" == resp.status
    data = json.loads(resp.data)
    assert "ok" == data["status"]
    assert "user1key" == data["user"]["apikey"]


@with_script_context
def test_user_lookup_handler_missing(ctx):
    # type: (ScriptContext) -> None
    values = {"format": "json", "client": "app1key", "user": "xxx"}
    builder = EnvironBuilder(method="POST", data=values)
    handler = UserLookupHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    assert "400 BAD REQUEST" == resp.status
    data = json.loads(resp.data)
    assert "error" == data["status"]
    assert 6 == data["error"]["code"]


def _cluster_secret_request(secret):
    # type: (Optional[str]) -> Request
    values = {"format": "json"}
    if secret is not None:
        values["secret"] = secret
    builder = EnvironBuilder(method="POST", data=values)
    return Request(builder.get_environ())


@with_script_context
def test_is_cluster_request_accepts_the_configured_secret(ctx):
    # type: (ScriptContext) -> None
    ctx.config.cluster.secret = "s3cr3t"
    handler = APIHandler(ctx)
    assert handler._is_cluster_request(_cluster_secret_request("s3cr3t")) is True


@with_script_context
def test_is_cluster_request_rejects_a_wrong_or_missing_secret(ctx):
    # type: (ScriptContext) -> None
    ctx.config.cluster.secret = "s3cr3t"
    handler = APIHandler(ctx)
    assert handler._is_cluster_request(_cluster_secret_request("wrong")) is False
    assert handler._is_cluster_request(_cluster_secret_request(None)) is False
    assert handler._is_cluster_request(_cluster_secret_request("")) is False


@with_script_context
def test_is_cluster_request_is_false_when_no_secret_is_configured(ctx):
    # type: (ScriptContext) -> None
    """Otherwise an unconfigured deployment would let anyone sending an empty
    secret past the rate limiter."""
    ctx.config.cluster.secret = None
    handler = APIHandler(ctx)
    assert handler._is_cluster_request(_cluster_secret_request(None)) is False
    assert handler._is_cluster_request(_cluster_secret_request("")) is False
    assert handler._is_cluster_request(_cluster_secret_request("anything")) is False


@with_script_context
def test_is_cluster_request_survives_a_non_ascii_secret(ctx):
    # type: (ScriptContext) -> None
    """compare_digest raises TypeError on a str with anything outside ASCII,
    and the value comes straight from the request."""
    ctx.config.cluster.secret = "s3cr3t"
    handler = APIHandler(ctx)
    assert handler._is_cluster_request(_cluster_secret_request("s3cr3té")) is False


@with_script_context
def test_cluster_requests_skip_the_rate_limiter(ctx):
    # type: (ScriptContext) -> None
    ctx.config.cluster.secret = "s3cr3t"

    class RateLimitedHandler(APIHandler):
        params_class = APIHandlerParams

        def _handle_internal(self, params):
            return {}

    handler = RateLimitedHandler(ctx)
    calls = []
    handler._rate_limit = lambda *args: calls.append(args)  # type: ignore[assignment]

    resp = handler.handle(_cluster_secret_request("s3cr3t"))
    assert "200 OK" == resp.status
    assert [] == calls

    resp = handler.handle(_cluster_secret_request("wrong"))
    assert "200 OK" == resp.status
    assert 1 == len(calls)


@with_script_context
def test_cluster_requests_touch_no_bucket_at_all(ctx):
    # type: (ScriptContext) -> None
    """Not just the IP bucket. The app bucket is keyed by the application being
    administered, so charging an admin request to it would refuse a request to
    disable a busy application because that application is busy; and limit()
    increments before it checks, so merely evaluating the global bucket would
    spend a paying application's budget on our own bookkeeping."""
    ctx.config.cluster.secret = "s3cr3t"
    buckets = []

    class RecordingRateLimiter:
        def __init__(self, *args, **kwargs):
            pass

        def limit(self, bucket, key, rate):
            buckets.append(bucket)
            return False

    class RateLimitedHandler(APIHandler):
        params_class = APIHandlerParams

        def _handle_internal(self, params):
            return {}

    with mock.patch("acoustid.api.v2.RateLimiter", RecordingRateLimiter):
        handler = RateLimitedHandler(ctx)
        assert "200 OK" == handler.handle(_cluster_secret_request("s3cr3t")).status
        assert [] == buckets

        assert "200 OK" == handler.handle(_cluster_secret_request("wrong")).status
        assert "global" in buckets
        assert "ip" in buckets


def lookup_values(**extra: str) -> MultiDict:
    """A lookup that is valid apart from whatever the test is varying."""
    values = MultiDict(
        {
            "format": "json",
            "client": "app1key",
            "duration": str(TEST_1_LENGTH),
            "fingerprint": TEST_1_FP,
        }
    )
    for name, value in extra.items():
        values[name] = value
    return values


@with_script_context
def test_lookup_accepts_no_user_key_before_the_cutover(ctx):
    # type: (ScriptContext) -> None
    """The window exists so clients can add a key before it is required."""
    params = LookupHandlerParams(ctx.config)
    with mock.patch.object(const, "LOOKUP_USER_REQUIRED_FROM", date(2099, 1, 1)):
        params.parse(lookup_values(), ctx.db)
    assert params.account_id is None


@with_script_context
def test_lookup_requires_a_user_key_from_the_cutover(ctx):
    # type: (ScriptContext) -> None
    """The whole point of the date: the same request stops being accepted."""
    params = LookupHandlerParams(ctx.config)
    with mock.patch.object(const, "LOOKUP_USER_REQUIRED_FROM", date(2000, 1, 1)):
        with pytest.raises(errors.MissingParameterError) as caught:
            params.parse(lookup_values(), ctx.db)
    assert caught.value.parameter == "user"


@with_script_context
def test_lookup_rejects_an_invalid_user_key_before_the_cutover(ctx):
    # type: (ScriptContext) -> None
    """A key that does not work is a caller bug now, not in 2027.

    This is the half that takes effect immediately, and it is the reason the
    change is worth shipping before the deadline: clients sending a stale or
    mistyped key find out while there is still time to fix it.
    """
    params = LookupHandlerParams(ctx.config)
    with mock.patch.object(const, "LOOKUP_USER_REQUIRED_FROM", date(2099, 1, 1)):
        assert_raises(
            errors.InvalidUserAPIKeyError,
            params.parse,
            lookup_values(user="N/A"),
            ctx.db,
        )


@with_script_context
def test_lookup_accepts_a_valid_user_key_and_resolves_the_account(ctx):
    # type: (ScriptContext) -> None
    params = LookupHandlerParams(ctx.config)
    with mock.patch.object(const, "LOOKUP_USER_REQUIRED_FROM", date(2099, 1, 1)):
        params.parse(lookup_values(user="user1key"), ctx.db)
    assert params.account_id == 1


@with_script_context
def test_lookup_treats_an_empty_user_key_as_absent(ctx):
    # type: (ScriptContext) -> None
    """`user=` is how a client that builds the parameter unconditionally and
    has nothing to put in it ends up sending it, so it has to mean the same as
    omitting it rather than being an invalid key."""
    params = LookupHandlerParams(ctx.config)
    with mock.patch.object(const, "LOOKUP_USER_REQUIRED_FROM", date(2099, 1, 1)):
        params.parse(lookup_values(user=""), ctx.db)
    assert params.account_id is None

    params = LookupHandlerParams(ctx.config)
    with mock.patch.object(const, "LOOKUP_USER_REQUIRED_FROM", date(2000, 1, 1)):
        with pytest.raises(errors.MissingParameterError) as caught:
            params.parse(lookup_values(user=""), ctx.db)
    assert caught.value.parameter == "user"


@with_script_context
def test_submissions_still_require_a_user_key_whatever_the_date(ctx):
    # type: (ScriptContext) -> None
    """The cutover is about lookups. Submissions have always required a user
    key, and moving the parsing to a shared method must not loosen that.

    Asserting on the parameter name rather than just the exception type,
    because a submission missing `user` is also missing a fingerprint and
    raises MissingParameterError either way. The first version of this test
    passed with the requirement removed entirely.
    """
    values = MultiDict(
        {
            "format": "json",
            "client": "app1key",
            "duration": str(TEST_1_LENGTH),
            "fingerprint": TEST_1_FP,
            "bitrate": "192",
            "fileformat": "MP3",
        }
    )
    params = SubmitHandlerParams(ctx.config)
    with mock.patch.object(const, "LOOKUP_USER_REQUIRED_FROM", date(2099, 1, 1)):
        with pytest.raises(errors.MissingParameterError) as caught:
            params.parse(values, ctx.db)
    assert caught.value.parameter == "user"


@with_script_context
def test_lookup_skips_the_user_key_for_an_exempt_application(ctx):
    # type: (ScriptContext) -> None
    """An exempt application's lookups work after the cutover without a key.

    This is the whole point of the column: commercial keys are billed to the
    application, so there is nobody for a user key to identify, and the
    announced policy does not apply to them.
    """
    app_db = ctx.db.get_app_db()
    app_db.execute(
        schema.application.update()
        .where(schema.application.c.apikey == "app1key")
        .values(requires_user_key=False)
    )
    app_user_key_policy_cache.clear()

    params = LookupHandlerParams(ctx.config)
    with mock.patch.object(const, "LOOKUP_USER_REQUIRED_FROM", date(2000, 1, 1)):
        params.parse(lookup_values(), ctx.db)
    assert params.account_id is None


@with_script_context
def test_an_exempt_application_still_cannot_send_a_bad_user_key(ctx):
    # type: (ScriptContext) -> None
    """Exemption is from needing a key, not from the key being checked."""
    app_db = ctx.db.get_app_db()
    app_db.execute(
        schema.application.update()
        .where(schema.application.c.apikey == "app1key")
        .values(requires_user_key=False)
    )
    app_user_key_policy_cache.clear()

    params = LookupHandlerParams(ctx.config)
    with mock.patch.object(const, "LOOKUP_USER_REQUIRED_FROM", date(2000, 1, 1)):
        assert_raises(
            errors.InvalidUserAPIKeyError,
            params.parse,
            lookup_values(user="N/A"),
            ctx.db,
        )


@with_script_context
def test_applications_require_a_user_key_unless_told_otherwise(ctx):
    # type: (ScriptContext) -> None
    """The default is the policy, so a new application needs no configuring."""
    app_user_key_policy_cache.clear()
    params = LookupHandlerParams(ctx.config)
    with mock.patch.object(const, "LOOKUP_USER_REQUIRED_FROM", date(2000, 1, 1)):
        with pytest.raises(errors.MissingParameterError) as caught:
            params.parse(lookup_values(), ctx.db)
    assert caught.value.parameter == "user"


def application_flag(ctx, application_id):
    # type: (ScriptContext, int) -> bool
    return bool(
        ctx.db.get_app_db()
        .execute(
            sql.select(schema.application.c.requires_user_key).where(
                schema.application.c.id == application_id
            )
        )
        .scalar()
    )


@with_script_context
def test_create_application_can_issue_an_exempt_key(ctx):
    # type: (ScriptContext) -> None
    """acoustid.biz issues keys through this endpoint, and its keys are exempt.

    Sent as "" rather than "false" because that is the convention this API
    already uses with that client -- see `active` in its hourly key sync.
    """
    ctx.config.cluster.secret = "s3cr3t"
    handler = CreateApplicationHandler(ctx)
    params = CreateApplicationHandlerParams(ctx.config)
    params.parse(
        MultiDict(
            {
                "secret": "s3cr3t",
                "account_id": "1",
                "name": "Commercial App",
                "version": "1.0",
                "requires_user_key": "",
            }
        ),
        ctx.db,
    )
    result = handler._handle_internal(params)
    assert application_flag(ctx, result["id"]) is False


@with_script_context
def test_create_application_requires_a_user_key_by_default(ctx):
    # type: (ScriptContext) -> None
    """Omitting the parameter must not create an exempt application."""
    ctx.config.cluster.secret = "s3cr3t"
    handler = CreateApplicationHandler(ctx)
    params = CreateApplicationHandlerParams(ctx.config)
    params.parse(
        MultiDict(
            {
                "secret": "s3cr3t",
                "account_id": "1",
                "name": "Normal App",
                "version": "1.0",
            }
        ),
        ctx.db,
    )
    result = handler._handle_internal(params)
    assert application_flag(ctx, result["id"]) is True


@with_script_context
def test_update_application_status_can_exempt_an_existing_application(ctx):
    # type: (ScriptContext) -> None
    """How the applications that already exist get exempted.

    acoustid.biz calls this hourly for every key it manages, so adding the
    parameter there is enough to cover its whole estate without a backfill.
    """
    ctx.config.cluster.secret = "s3cr3t"
    handler = UpdateApplicationStatusHandler(ctx)
    params = UpdateApplicationStatusHandlerParams(ctx.config)
    params.parse(
        MultiDict(
            {
                "secret": "s3cr3t",
                "account_id": "1",
                "application_id": "1",
                "active": "1",
                "requires_user_key": "",
            }
        ),
        ctx.db,
    )
    handler._handle_internal(params)
    assert application_flag(ctx, 1) is False


@with_script_context
def test_update_application_status_leaves_the_flag_alone_when_omitted(ctx):
    # type: (ScriptContext) -> None
    """The existing hourly sync sends only `active` and must stay harmless.

    If omission meant false, every run of acoustid.biz's key sync would exempt
    every application it touches -- the opposite of the policy, applied
    silently and hourly.
    """
    ctx.db.get_app_db().execute(
        schema.application.update()
        .where(schema.application.c.id == 1)
        .values(requires_user_key=False)
    )

    ctx.config.cluster.secret = "s3cr3t"
    handler = UpdateApplicationStatusHandler(ctx)
    params = UpdateApplicationStatusHandlerParams(ctx.config)
    params.parse(
        MultiDict(
            {
                "secret": "s3cr3t",
                "account_id": "1",
                "application_id": "1",
                "active": "1",
            }
        ),
        ctx.db,
    )
    handler._handle_internal(params)
    assert application_flag(ctx, 1) is False
