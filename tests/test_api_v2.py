# Copyright (C) 2011,2012 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import json
import unittest
from typing import Any, Dict

from werkzeug.datastructures import MultiDict
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from acoustid import tables
from acoustid.api import errors
from acoustid.api.v2 import (
    APIHandler,
    APIHandlerParams,
    FingerprintLookupQuery,
    LookupHandler,
    LookupHandlerParams,
    SubmitHandler,
    SubmitHandlerParams,
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


@unittest.skip("disabled")
@with_script_context
def test_lookup_handler(ctx):
    # type: (ScriptContext) -> None
    values = {
        "format": "json",
        "client": "app1key",
        "duration": str(TEST_1_LENGTH),
        "fingerprint": TEST_1_FP,
    }
    builder = EnvironBuilder(method="POST", data=values)
    handler = LookupHandler(ctx)
    # no matches
    handler = LookupHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "application/json; charset=UTF-8" == resp.content_type
    expected = {"status": "ok", "results": []}  # type: Dict[str, Any]
    assert_json_equals(expected, resp.data)
    assert "200 OK" == resp.status
    # one exact match
    prepare_database(
        ctx,
        """
INSERT INTO fingerprint (length, fingerprint, track_id, submission_count)
    VALUES (%s, %s, 1, 1);
""",
        (TEST_1_LENGTH, TEST_1_FP_RAW),
    )
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
        ctx,
        "INSERT INTO track_mbid (track_id, mbid, submission_count) VALUES (1, '373e6728-35e3-4633-aab1-bf7092ec43d8', 1)",
    )
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
                        "id": "373e6728-35e3-4633-aab1-bf7092ec43d8",
                    },
                    {
                        "id": "b81f83ee-4da4-11e0-9ed8-0025225356f3",
                        "duration": 123,
                        "tracks": [
                            {
                                "title": "Track A",
                                "duration": 123,
                                "position": 1,
                                "medium": {
                                    "track_count": 2,
                                    "position": 1,
                                    "format": "DVD",
                                    "release": {
                                        "id": "1d4d546f-e2ec-4553-8df7-9004298924d5",
                                        "title": "Album A",
                                    },
                                },
                                "artists": [
                                    {
                                        "id": "a64796c0-4da4-11e0-bf81-0025225356f3",
                                        "name": "Artist A",
                                    }
                                ],
                            },
                            {
                                "title": "Track A",
                                "duration": 123,
                                "position": 1,
                                "medium": {
                                    "track_count": 2,
                                    "position": 1,
                                    "format": "CD",
                                    "release": {
                                        "id": "dd6c2cca-a0e9-4cc4-9a5f-7170bd098e23",
                                        "title": "Album A",
                                    },
                                },
                                "artists": [
                                    {
                                        "id": "a64796c0-4da4-11e0-bf81-0025225356f3",
                                        "name": "Artist A",
                                    }
                                ],
                            },
                        ],
                    },
                ],
            }
        ],
    }
    assert_json_equals(expected, resp.data)
    assert "200 OK" == resp.status
    # duplicate fingerprint
    prepare_database(
        ctx,
        """
INSERT INTO fingerprint (length, fingerprint, track_id, submission_count)
    VALUES (%s, %s, 1, 1);
""",
        (TEST_1_LENGTH, TEST_1_FP_RAW),
    )
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
    assert "b9c05616-1874-4d5d-b30e-6b959c922d28" == submission["mbid"]
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
    assert "b9c05616-1874-4d5d-b30e-6b959c922d28" == submission["mbid"]
    assert submission["meta_id"] is None
    assert submission["meta_gid"] is None
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
    assert "b9c05616-1874-4d5d-b30e-6b959c922d28" == submission["puid"]
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
