# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import unittest
from nose.tools import assert_equals, assert_raises
import tests
from tests import (
    prepare_database, with_database,
    TEST_1_LENGTH,
    TEST_1_FP,
    TEST_1_FP_RAW,
    TEST_2_LENGTH,
    TEST_2_FP,
    TEST_2_FP_RAW,
)
from werkzeug.wrappers import Request
from werkzeug.test import EnvironBuilder
from werkzeug.datastructures import MultiDict
from acoustid import tables
from acoustid.api import errors
from acoustid.api.v1 import (
    LookupHandler,
    LookupHandlerParams,
    SubmitHandler,
    SubmitHandlerParams,
    APIHandler,
)


def test_ok():
    handler = APIHandler()
    resp = handler._ok({'tracks': [{'id': 1, 'name': 'Track 1'}]})
    assert_equals('text/xml; charset=UTF-8', resp.content_type)
    expected = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n<response status="ok"><tracks><track><id>1</id><name>Track 1</name></track></tracks></response>'
    assert_equals(expected, resp.data)
    assert_equals('200 OK', resp.status)


def test_error():
    handler = APIHandler()
    resp = handler._error(123, 'something is wrong')
    assert_equals('text/xml; charset=UTF-8', resp.content_type)
    expected = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n<response status="error"><error>something is wrong</error></response>'
    assert_equals(expected, resp.data)
    assert_equals('400 BAD REQUEST', resp.status)
    resp = handler._error(234, 'oops', status=500)
    assert_equals('text/xml; charset=UTF-8', resp.content_type)
    expected = '<?xml version=\'1.0\' encoding=\'UTF-8\'?>\n<response status="error"><error>oops</error></response>'
    assert_equals(expected, resp.data)
    assert_equals('500 INTERNAL SERVER ERROR', resp.status)


@with_database
def test_lookup_handler_params(conn):
    # missing client
    values = MultiDict({})
    params = LookupHandlerParams(tests.script.config)
    assert_raises(errors.MissingParameterError, params.parse, values, conn)
    # invalid client
    values = MultiDict({'client': 'N/A'})
    params = LookupHandlerParams(tests.script.config)
    assert_raises(errors.InvalidAPIKeyError, params.parse, values, conn)
    # missing length
    values = MultiDict({'client': 'app1key'})
    params = LookupHandlerParams(tests.script.config)
    assert_raises(errors.MissingParameterError, params.parse, values, conn)
    # missing fingerprint
    values = MultiDict({'client': 'app1key', 'length': str(TEST_1_LENGTH)})
    params = LookupHandlerParams(tests.script.config)
    assert_raises(errors.MissingParameterError, params.parse, values, conn)
    # invalid fingerprint
    values = MultiDict({'client': 'app1key', 'length': str(TEST_1_LENGTH), 'fingerprint': '...'})
    params = LookupHandlerParams(tests.script.config)
    assert_raises(errors.InvalidFingerprintError, params.parse, values, conn)
    # all ok
    values = MultiDict({'client': 'app1key', 'length': str(TEST_1_LENGTH), 'fingerprint': TEST_1_FP})
    params = LookupHandlerParams(tests.script.config)
    params.parse(values, conn)
    assert_equals(1, params.application_id)
    assert_equals(TEST_1_LENGTH, params.fingerprints[0]['duration'])
    assert_equals(TEST_1_FP_RAW, params.fingerprints[0]['fingerprint'])


@with_database
@unittest.skip("disabled")
def lookup_handler(conn):
    values = {'client': 'app1key', 'length': str(TEST_1_LENGTH), 'fingerprint': TEST_1_FP}
    builder = EnvironBuilder(method='POST', data=values)
    # no matches
    handler = LookupHandler.create_from_server(tests.script, conn=conn)
    resp = handler.handle(Request(builder.get_environ()))
    assert_equals('text/xml; charset=UTF-8', resp.content_type)
    expected = "<?xml version='1.0' encoding='UTF-8'?>\n<response><status>ok</status><results /></response>"
    assert_equals(expected, resp.data)
    assert_equals('200 OK', resp.status)
    # one exact match
    prepare_database(conn, """
INSERT INTO fingerprint (length, fingerprint, track_id, submission_count)
    VALUES (%s, %s, 1, 1);
""", (TEST_1_LENGTH, TEST_1_FP_RAW))
    handler = LookupHandler.create_from_server(tests.script, conn=conn)
    resp = handler.handle(Request(builder.get_environ()))
    assert_equals('text/xml; charset=UTF-8', resp.content_type)
    expected = "<?xml version='1.0' encoding='UTF-8'?>\n<response><status>ok</status><results><result><score>1.0</score><id>eb31d1c3-950e-468b-9e36-e46fa75b1291</id></result></results></response>"
    assert_equals(expected, resp.data)
    assert_equals('200 OK', resp.status)
    # one exact match with MBIDs
    values = {'client': 'app1key', 'length': str(TEST_1_LENGTH), 'fingerprint': TEST_1_FP, 'meta': '1'}
    builder = EnvironBuilder(method='POST', data=values)
    handler = LookupHandler.create_from_server(tests.script, conn=conn)
    resp = handler.handle(Request(builder.get_environ()))
    assert_equals('text/xml; charset=UTF-8', resp.content_type)
    expected = "<?xml version='1.0' encoding='UTF-8'?>\n<response><status>ok</status><results><result><tracks><track><id>b81f83ee-4da4-11e0-9ed8-0025225356f3</id></track></tracks><score>1.0</score><id>eb31d1c3-950e-468b-9e36-e46fa75b1291</id></result></results></response>"
    assert_equals(expected, resp.data)
    assert_equals('200 OK', resp.status)
    # one exact match with MBIDs (no exta metadata in v1)
    values = {'client': 'app1key', 'length': str(TEST_1_LENGTH), 'fingerprint': TEST_1_FP, 'meta': '2'}
    builder = EnvironBuilder(method='POST', data=values)
    handler = LookupHandler.create_from_server(tests.script, conn=conn)
    resp = handler.handle(Request(builder.get_environ()))
    assert_equals('text/xml; charset=UTF-8', resp.content_type)
    expected = "<?xml version='1.0' encoding='UTF-8'?>\n<response><status>ok</status><results><result><tracks><track><id>b81f83ee-4da4-11e0-9ed8-0025225356f3</id></track></tracks><score>1.0</score><id>eb31d1c3-950e-468b-9e36-e46fa75b1291</id></result></results></response>"
    assert_equals(expected, resp.data)
    assert_equals('200 OK', resp.status)


@with_database
def test_submit_handler_params(conn):
    # missing client
    values = MultiDict({})
    params = SubmitHandlerParams(tests.script.config)
    assert_raises(errors.MissingParameterError, params.parse, values, conn)
    # invalid client
    values = MultiDict({'client': 'N/A'})
    params = SubmitHandlerParams(tests.script.config)
    assert_raises(errors.InvalidAPIKeyError, params.parse, values, conn)
    # missing user
    values = MultiDict({'client': 'app1key'})
    params = SubmitHandlerParams(tests.script.config)
    assert_raises(errors.MissingParameterError, params.parse, values, conn)
    # invalid user
    values = MultiDict({'client': 'app1key', 'user': 'N/A'})
    params = SubmitHandlerParams(tests.script.config)
    assert_raises(errors.InvalidUserAPIKeyError, params.parse, values, conn)
    # missing fingerprint
    values = MultiDict({'client': 'app1key', 'user': 'user1key'})
    params = SubmitHandlerParams(tests.script.config)
    assert_raises(errors.MissingParameterError, params.parse, values, conn)
    # missing duration
    values = MultiDict({'client': 'app1key', 'user': 'user1key',
        'mbid': ['4d814cb1-20ec-494f-996f-f31ca8a49784', '66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea'],
        'puid': '4e823498-c77d-4bfb-b6cc-85b05c2783cf',
        'fingerprint': TEST_1_FP,
        'bitrate': '192',
        'format': 'MP3'
    })
    params = SubmitHandlerParams(tests.script.config)
    assert_raises(errors.MissingParameterError, params.parse, values, conn)
    # all ok (single submission)
    values = MultiDict({'client': 'app1key', 'user': 'user1key',
        'mbid': ['4d814cb1-20ec-494f-996f-f31ca8a49784', '66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea'],
        'puid': '4e823498-c77d-4bfb-b6cc-85b05c2783cf',
        'length': str(TEST_1_LENGTH),
        'fingerprint': TEST_1_FP,
        'bitrate': '192',
        'format': 'MP3'
    })
    params = SubmitHandlerParams(tests.script.config)
    params.parse(values, conn)
    assert_equals(1, len(params.submissions))
    assert_equals(['4d814cb1-20ec-494f-996f-f31ca8a49784', '66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea'], params.submissions[0]['mbids'])
    assert_equals('4e823498-c77d-4bfb-b6cc-85b05c2783cf', params.submissions[0]['puid'])
    assert_equals(TEST_1_LENGTH, params.submissions[0]['duration'])
    assert_equals(TEST_1_FP_RAW, params.submissions[0]['fingerprint'])
    assert_equals(192, params.submissions[0]['bitrate'])
    assert_equals('MP3', params.submissions[0]['format'])
    # all ok (single submission)
    values = MultiDict({
        'client': 'app1key', 'user': 'user1key',
        'mbid.0': '4d814cb1-20ec-494f-996f-f31ca8a49784',
        'puid.0': '4e823498-c77d-4bfb-b6cc-85b05c2783cf',
        'length.0': str(TEST_1_LENGTH),
        'fingerprint.0': TEST_1_FP,
        'bitrate.0': '192',
        'format.0': 'MP3',
        'mbid.1': '66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea',
        'puid.1': '57b202a3-242b-4896-a79c-cac34bbca0b6',
        'length.1': str(TEST_2_LENGTH),
        'fingerprint.1': TEST_2_FP,
        'bitrate.1': '500',
        'format.1': 'FLAC',
    })
    params = SubmitHandlerParams(tests.script.config)
    params.parse(values, conn)
    assert_equals(2, len(params.submissions))
    assert_equals(['4d814cb1-20ec-494f-996f-f31ca8a49784'], params.submissions[0]['mbids'])
    assert_equals('4e823498-c77d-4bfb-b6cc-85b05c2783cf', params.submissions[0]['puid'])
    assert_equals(TEST_1_LENGTH, params.submissions[0]['duration'])
    assert_equals(TEST_1_FP_RAW, params.submissions[0]['fingerprint'])
    assert_equals(192, params.submissions[0]['bitrate'])
    assert_equals('MP3', params.submissions[0]['format'])
    assert_equals(['66c0f5cc-67b6-4f51-80cd-ab26b5aaa6ea'], params.submissions[1]['mbids'])
    assert_equals('57b202a3-242b-4896-a79c-cac34bbca0b6', params.submissions[1]['puid'])
    assert_equals(TEST_2_LENGTH, params.submissions[1]['duration'])
    assert_equals(TEST_2_FP_RAW, params.submissions[1]['fingerprint'])
    assert_equals(500, params.submissions[1]['bitrate'])
    assert_equals('FLAC', params.submissions[1]['format'])


@with_database
def test_submit_handler(conn):
    values = {'client': 'app1key', 'user': 'user1key',
        'length': str(TEST_1_LENGTH), 'fingerprint': TEST_1_FP, 'bitrate': 192,
        'mbid': 'b9c05616-1874-4d5d-b30e-6b959c922d28', 'format': 'FLAC'}
    builder = EnvironBuilder(method='POST', data=values)
    handler = SubmitHandler.create_from_server(tests.script, conn=conn)
    resp = handler.handle(Request(builder.get_environ()))
    assert_equals('text/xml; charset=UTF-8', resp.content_type)
    expected = "<?xml version='1.0' encoding='UTF-8'?>\n<response><status>ok</status><submissions><submission><status>pending</status><id>1</id></submission></submissions></response>"
    assert_equals(expected, resp.data)
    assert_equals('200 OK', resp.status)
    query = tables.submission.select().order_by(tables.submission.c.id.desc()).limit(1)
    submission = conn.execute(query).fetchone()
    assert_equals('b9c05616-1874-4d5d-b30e-6b959c922d28', submission['mbid'])
    assert_equals(1, submission['format_id'])
    assert_equals(192, submission['bitrate'])
    assert_equals(TEST_1_FP_RAW, submission['fingerprint'])
    assert_equals(TEST_1_LENGTH, submission['length'])
