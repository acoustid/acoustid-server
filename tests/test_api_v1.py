# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from werkzeug.datastructures import MultiDict
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from acoustid import tables
from acoustid.api import errors
from acoustid.api.v1 import (
    APIHandler,
    LookupHandler,
    LookupHandlerParams,
    SubmitHandler,
    SubmitHandlerParams,
)
from acoustid.api.v2 import FingerprintLookupQuery
from acoustid.script import ScriptContext
from tests import (
    TEST_1_FP,
    TEST_1_FP_RAW,
    TEST_1_LENGTH,
    TEST_2_FP,
    TEST_2_FP_RAW,
    TEST_2_LENGTH,
    assert_raises,
    prepare_database,
    with_script_context,
)


@with_script_context
def test_ok(ctx):
    # type: (ScriptContext) -> None
    handler = APIHandler(ctx)
    resp = handler._ok({"tracks": [{"id": 1, "name": "Track 1"}]})
    assert "text/xml; charset=UTF-8" == resp.content_type
    expected = b"<?xml version='1.0' encoding='UTF-8'?>\n<response status=\"ok\"><tracks><track><id>1</id><name>Track 1</name></track></tracks></response>"
    assert expected == resp.data
    assert "200 OK" == resp.status


@with_script_context
def test_error(ctx):
    # type: (ScriptContext) -> None
    handler = APIHandler(ctx)
    resp = handler._error(123, "something is wrong")
    assert "text/xml; charset=UTF-8" == resp.content_type
    expected = b"<?xml version='1.0' encoding='UTF-8'?>\n<response status=\"error\"><error>something is wrong</error></response>"
    assert expected == resp.data
    assert "400 BAD REQUEST" == resp.status
    resp = handler._error(234, "oops", status=500)
    assert "text/xml; charset=UTF-8" == resp.content_type
    expected = b"<?xml version='1.0' encoding='UTF-8'?>\n<response status=\"error\"><error>oops</error></response>"
    assert expected == resp.data
    assert "500 INTERNAL SERVER ERROR" == resp.status


@with_script_context
def test_lookup_handler_params(ctx):
    # type: (ScriptContext) -> None
    # missing client
    values = MultiDict({})  # type: MultiDict
    params = LookupHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # invalid client
    values = MultiDict({"client": "N/A"})
    params = LookupHandlerParams(ctx.config)
    assert_raises(errors.InvalidAPIKeyError, params.parse, values, ctx.db)
    # missing length
    values = MultiDict({"client": "app1key"})
    params = LookupHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # missing fingerprint
    values = MultiDict({"client": "app1key", "length": str(TEST_1_LENGTH)})
    params = LookupHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # invalid fingerprint
    values = MultiDict(
        {"client": "app1key", "length": str(TEST_1_LENGTH), "fingerprint": "..."}
    )
    params = LookupHandlerParams(ctx.config)
    assert_raises(errors.InvalidFingerprintError, params.parse, values, ctx.db)
    # all ok
    values = MultiDict(
        {"client": "app1key", "length": str(TEST_1_LENGTH), "fingerprint": TEST_1_FP}
    )
    params = LookupHandlerParams(ctx.config)
    params.parse(values, ctx.db)
    assert 1 == params.application_id
    assert len(params.fingerprints) == 1
    assert isinstance(params.fingerprints[0], FingerprintLookupQuery)
    assert TEST_1_LENGTH == params.fingerprints[0].duration
    assert TEST_1_FP_RAW == params.fingerprints[0].fingerprint


@with_script_context
def lookup_handler(ctx):
    # type: (ScriptContext) -> None
    values = {
        "client": "app1key",
        "length": str(TEST_1_LENGTH),
        "fingerprint": TEST_1_FP,
    }
    builder = EnvironBuilder(method="POST", data=values)
    # no matches
    handler = LookupHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "text/xml; charset=UTF-8" == resp.content_type
    expected = "<?xml version='1.0' encoding='UTF-8'?>\n<response><status>ok</status><results /></response>"
    assert expected == resp.data
    assert "200 OK" == resp.status
    # one exact match
    prepare_database(
        ctx.db.get_fingerprint_db(),
        """
INSERT INTO fingerprint (length, fingerprint, track_id, submission_count)
    VALUES (%s, %s, 1, 1);
""",
        (TEST_1_LENGTH, TEST_1_FP_RAW),
    )
    handler = LookupHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "text/xml; charset=UTF-8" == resp.content_type
    expected = "<?xml version='1.0' encoding='UTF-8'?>\n<response><status>ok</status><results><result><score>1.0</score><id>eb31d1c3-950e-468b-9e36-e46fa75b1291</id></result></results></response>"
    assert expected == resp.data
    assert "200 OK" == resp.status
    # one exact match with MBIDs
    values = {
        "client": "app1key",
        "length": str(TEST_1_LENGTH),
        "fingerprint": TEST_1_FP,
        "meta": "1",
    }
    builder = EnvironBuilder(method="POST", data=values)
    handler = LookupHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "text/xml; charset=UTF-8" == resp.content_type
    expected = "<?xml version='1.0' encoding='UTF-8'?>\n<response><status>ok</status><results><result><tracks><track><id>b81f83ee-4da4-11e0-9ed8-0025225356f3</id></track></tracks><score>1.0</score><id>eb31d1c3-950e-468b-9e36-e46fa75b1291</id></result></results></response>"
    assert expected == resp.data
    assert "200 OK" == resp.status
    # one exact match with MBIDs (no exta metadata in v1)
    values = {
        "client": "app1key",
        "length": str(TEST_1_LENGTH),
        "fingerprint": TEST_1_FP,
        "meta": "2",
    }
    builder = EnvironBuilder(method="POST", data=values)
    handler = LookupHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "text/xml; charset=UTF-8" == resp.content_type
    expected = "<?xml version='1.0' encoding='UTF-8'?>\n<response><status>ok</status><results><result><tracks><track><id>b81f83ee-4da4-11e0-9ed8-0025225356f3</id></track></tracks><score>1.0</score><id>eb31d1c3-950e-468b-9e36-e46fa75b1291</id></result></results></response>"
    assert expected == resp.data
    assert "200 OK" == resp.status


@with_script_context
def test_submit_handler_params(ctx):
    # type: (ScriptContext) -> None
    # missing client
    values = MultiDict({})  # type: MultiDict
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # invalid client
    values = MultiDict({"client": "N/A"})
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.InvalidAPIKeyError, params.parse, values, ctx.db)
    # missing user
    values = MultiDict({"client": "app1key"})
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # invalid user
    values = MultiDict({"client": "app1key", "user": "N/A"})
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.InvalidUserAPIKeyError, params.parse, values, ctx.db)
    # missing fingerprint
    values = MultiDict({"client": "app1key", "user": "user1key"})
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # missing duration
    values = MultiDict(
        {
            "client": "app1key",
            "user": "user1key",
            "mbid": [
                "4d814cb1-20ec-494f-996f-f31ca8a49784",
                "66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea",
            ],
            "puid": "4e823498-c77d-4bfb-b6cc-85b05c2783cf",
            "fingerprint": TEST_1_FP,
            "bitrate": "192",
            "format": "MP3",
        }
    )
    params = SubmitHandlerParams(ctx.config)
    assert_raises(errors.MissingParameterError, params.parse, values, ctx.db)
    # all ok (single submission)
    values = MultiDict(
        {
            "client": "app1key",
            "user": "user1key",
            "mbid": [
                "4d814cb1-20ec-494f-996f-f31ca8a49784",
                "66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea",
            ],
            "puid": "4e823498-c77d-4bfb-b6cc-85b05c2783cf",
            "length": str(TEST_1_LENGTH),
            "fingerprint": TEST_1_FP,
            "bitrate": "192",
            "format": "MP3",
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
    assert TEST_1_LENGTH == params.submissions[0]["duration"]
    assert TEST_1_FP_RAW == params.submissions[0]["fingerprint"]
    assert 192 == params.submissions[0]["bitrate"]
    assert "MP3" == params.submissions[0]["format"]
    # all ok (single submission)
    values = MultiDict(
        {
            "client": "app1key",
            "user": "user1key",
            "mbid.0": "4d814cb1-20ec-494f-996f-f31ca8a49784",
            "puid.0": "4e823498-c77d-4bfb-b6cc-85b05c2783cf",
            "length.0": str(TEST_1_LENGTH),
            "fingerprint.0": TEST_1_FP,
            "bitrate.0": "192",
            "format.0": "MP3",
            "mbid.1": "66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea",
            "puid.1": "57b202a3-242b-4896-a79c-cac34bbca0b6",
            "length.1": str(TEST_2_LENGTH),
            "fingerprint.1": TEST_2_FP,
            "bitrate.1": "500",
            "format.1": "FLAC",
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


@with_script_context
def test_submit_handler(ctx):
    # type: (ScriptContext) -> None
    values = {
        "client": "app1key",
        "user": "user1key",
        "length": str(TEST_1_LENGTH),
        "fingerprint": TEST_1_FP,
        "bitrate": 192,
        "mbid": "b9c05616-1874-4d5d-b30e-6b959c922d28",
        "format": "FLAC",
    }
    builder = EnvironBuilder(method="POST", data=values)
    handler = SubmitHandler(ctx)
    resp = handler.handle(Request(builder.get_environ()))
    assert "text/xml; charset=UTF-8" == resp.content_type
    expected = b"<?xml version='1.0' encoding='UTF-8'?>\n<response><status>ok</status><submissions><submission><id>1</id><status>pending</status></submission></submissions></response>"
    assert expected == resp.data
    assert "200 OK" == resp.status
    query = tables.submission.select().order_by(tables.submission.c.id.desc()).limit(1)
    submission = ctx.db.get_ingest_db().execute(query).fetchone()
    assert "b9c05616-1874-4d5d-b30e-6b959c922d28" == submission["mbid"]
    assert "FLAC" == submission["format"]
    assert 192 == submission["bitrate"]
    assert TEST_1_FP_RAW == submission["fingerprint"]
    assert TEST_1_LENGTH == submission["length"]
