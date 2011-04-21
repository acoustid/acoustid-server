# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import *
from tests import (
    prepare_database, with_database,
    TEST_1_FP_RAW,
    TEST_1_LENGTH,
    TEST_2_FP_RAW,
    TEST_2_LENGTH,
)
from acoustid import tables
from acoustid.data.submission import insert_submission, import_submission, import_queued_submissions


@with_database
def test_insert_submission(conn):
    id = insert_submission(conn, {
        'fingerprint': [1,2,3,4,5,6],
        'length': 123,
        'bitrate': 192,
        'source_id': 1,
        'format_id': 1,
    })
    assert_equals(1, id)
    rows = conn.execute("""
        SELECT fingerprint, length, bitrate, source_id, format_id
        FROM submission WHERE id=%s
    """, (id,)).fetchall()
    expected_rows = [
        ([1,2,3,4,5,6], 123, 192, 1, 1),
    ]
    assert_equals(expected_rows, rows)


@with_database
def test_import_submission(conn):
    # first submission
    id = insert_submission(conn, {
        'fingerprint': TEST_1_FP_RAW,
        'length': TEST_1_LENGTH,
        'bitrate': 192,
        'source_id': 1,
        'format_id': 1,
        'mbid': '1f143d2b-db04-47cc-82a0-eee6efaa1142',
        'puid': '7c1c6753-c834-44b1-884a-a5166c093139',
    })
    query = tables.submission.select(tables.submission.c.id == id)
    submission = conn.execute(query).fetchone()
    assert_false(submission['handled'])
    fingerprint = import_submission(conn, submission)
    assert_equals(1, fingerprint['id'])
    assert_equals(5, fingerprint['track_id'])
    query = tables.submission.select(tables.submission.c.id == id)
    submission = conn.execute(query).fetchone()
    assert_true(submission['handled'])
    # second submission
    id = insert_submission(conn, {
        'fingerprint': TEST_2_FP_RAW,
        'length': TEST_2_LENGTH,
        'bitrate': 192,
        'source_id': 1,
        'format_id': 1,
    })
    query = tables.submission.select(tables.submission.c.id == id)
    submission = conn.execute(query).fetchone()
    assert_false(submission['handled'])
    fingerprint = import_submission(conn, submission)
    assert_equals(2, fingerprint['id'])
    assert_equals(6, fingerprint['track_id'])
    query = tables.submission.select(tables.submission.c.id == id)
    submission = conn.execute(query).fetchone()
    assert_true(submission['handled'])
    # third submission (same as the first one)
    id = insert_submission(conn, {
        'fingerprint': TEST_1_FP_RAW,
        'length': TEST_1_LENGTH,
        'bitrate': 192,
        'source_id': 1,
        'format_id': 1,
        'mbid': '1f143d2b-db04-47cc-82a0-eee6efaa1142',
        'puid': '7c1c6753-c834-44b1-884a-a5166c093139',
    })
    query = tables.submission.select(tables.submission.c.id == id)
    submission = conn.execute(query).fetchone()
    assert_false(submission['handled'])
    fingerprint = import_submission(conn, submission)
    assert_equals(1, fingerprint['id'])
    assert_equals(5, fingerprint['track_id'])
    query = tables.submission.select(tables.submission.c.id == id)
    submission = conn.execute(query).fetchone()
    assert_true(submission['handled'])


@with_database
def test_import_queued_submissions(conn):
    insert_submission(conn, {
        'fingerprint': TEST_1_FP_RAW,
        'length': TEST_1_LENGTH,
        'bitrate': 192,
        'source_id': 1,
        'format_id': 1,
    })
    insert_submission(conn, {
        'fingerprint': TEST_2_FP_RAW,
        'length': TEST_2_LENGTH,
        'bitrate': 192,
        'source_id': 1,
        'format_id': 1,
    })
    insert_submission(conn, {
        'fingerprint': TEST_1_FP_RAW,
        'length': TEST_1_LENGTH,
        'bitrate': 192,
        'source_id': 1,
        'format_id': 1,
    })
    import_queued_submissions(conn)
    count = conn.execute("SELECT count(*) FROM fingerprint WHERE id IN (1,2,3)").scalar()
    assert_equals(2, count)
    count = conn.execute("SELECT count(*) FROM track WHERE id IN (5,6,7)").scalar()
    assert_equals(2, count)

