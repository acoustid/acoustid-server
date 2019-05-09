# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

from nose.tools import assert_equals, assert_false, assert_true
from tests import (
    prepare_database, with_database,
    TEST_1_FP_RAW,
    TEST_1_LENGTH,
    TEST_1A_FP_RAW,
    TEST_1A_LENGTH,
    TEST_1B_FP_RAW,
    TEST_1B_LENGTH,
    TEST_1C_FP_RAW,
    TEST_1C_LENGTH,
    TEST_1D_FP_RAW,
    TEST_1D_LENGTH,
    TEST_2_FP_RAW,
    TEST_2_LENGTH,
)
from acoustid import tables, const
from acoustid.data.meta import insert_meta
from acoustid.data.submission import insert_submission, import_submission, import_queued_submissions


@with_database
def test_insert_submission(conn):
    id = insert_submission(conn, {
        'fingerprint': [1, 2, 3, 4, 5, 6],
        'length': 123,
        'bitrate': 192,
        'source_id': 1,
        'format_id': 1,
    })
    assert_equals(1, id)
    rows = conn.execute("""
        SELECT fingerprint, length, bitrate, format_id
        FROM submission WHERE id=%s
    """, (id,)).fetchall()
    expected_rows = [
        ([1, 2, 3, 4, 5, 6], 123, 192, 1),
    ]
    assert_equals(expected_rows, rows)


@with_database
def test_import_submission_with_foreignid(conn):
    prepare_database(conn, """
    INSERT INTO foreignid_vendor (id, name) VALUES (1, 'foo');
    INSERT INTO foreignid (id, vendor_id, name) VALUES (1, 1, '123');
    """)
    id = insert_submission(conn, {
        'fingerprint': TEST_1_FP_RAW,
        'length': TEST_1_LENGTH,
        'bitrate': 192,
        'source_id': 1,
        'format_id': 1,
        'foreignid_id': 1,
    })
    query = tables.submission.select(tables.submission.c.id == id)
    submission = conn.execute(query).fetchone()
    fingerprint = import_submission(conn, submission)
    query = tables.track_foreignid.select(tables.track_foreignid.c.track_id == fingerprint['track_id'])
    track_foreignid = conn.execute(query).fetchone()
    assert_equals(1, track_foreignid['submission_count'])


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
    query = tables.track_mbid.select(tables.track_mbid.c.track_id == fingerprint['track_id'])
    track_mbid = conn.execute(query).fetchone()
    assert_equals(1, track_mbid['submission_count'])
    query = tables.track_puid.select(tables.track_puid.c.track_id == fingerprint['track_id'])
    track_puid = conn.execute(query).fetchone()
    assert_equals(1, track_puid['submission_count'])
    query = tables.fingerprint.select(tables.fingerprint.c.id == fingerprint['id'])
    fingerprint = conn.execute(query).fetchone()
    assert_equals(1, fingerprint['submission_count'])
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
    query = tables.track_mbid.select(tables.track_mbid.c.track_id == fingerprint['track_id'])
    track_mbid = conn.execute(query).fetchone()
    assert_equals(2, track_mbid['submission_count'])
    query = tables.track_puid.select(tables.track_puid.c.track_id == fingerprint['track_id'])
    track_puid = conn.execute(query).fetchone()
    assert_equals(2, track_puid['submission_count'])
    query = tables.fingerprint.select(tables.fingerprint.c.id == fingerprint['id'])
    fingerprint = conn.execute(query).fetchone()
    assert_equals(2, fingerprint['submission_count'])


@with_database
def test_import_submission_reuse_fingerprint_97(conn):
    prepare_database(conn, """
    INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
        VALUES (%(fp)s, %(len)s, 1, 1);
    """, dict(fp=TEST_1A_FP_RAW, len=TEST_1A_LENGTH))
    id = insert_submission(conn, {
        'fingerprint': TEST_1B_FP_RAW,
        'length': TEST_1B_LENGTH,
        'source_id': 1,
        'mbid': '1f143d2b-db04-47cc-82a0-eee6efaa1142',
        'puid': '7c1c6753-c834-44b1-884a-a5166c093139',
    })
    query = tables.submission.select(tables.submission.c.id == id)
    submission = conn.execute(query).fetchone()
    assert_false(submission['handled'])
    fingerprint = import_submission(conn, submission)
    assert_equals(1, fingerprint['id'])
    assert_equals(1, fingerprint['track_id'])


@with_database
def test_import_submission_reuse_fingerprint_100(conn):
    prepare_database(conn, """
    INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
        VALUES (%(fp)s, %(len)s, 1, 1);
    """, dict(fp=TEST_1A_FP_RAW, len=TEST_1A_LENGTH))
    id = insert_submission(conn, {
        'fingerprint': TEST_1A_FP_RAW,
        'length': TEST_1A_LENGTH,
        'source_id': 1,
        'mbid': '1f143d2b-db04-47cc-82a0-eee6efaa1142',
        'puid': '7c1c6753-c834-44b1-884a-a5166c093139',
    })
    query = tables.submission.select(tables.submission.c.id == id)
    submission = conn.execute(query).fetchone()
    assert_false(submission['handled'])
    fingerprint = import_submission(conn, submission)
    assert_equals(1, fingerprint['id'])
    assert_equals(1, fingerprint['track_id'])


@with_database
def test_import_submission_reuse_track_93(conn):
    prepare_database(conn, """
    INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
        VALUES (%(fp)s, %(len)s, 1, 1);
    """, dict(fp=TEST_1A_FP_RAW, len=TEST_1A_LENGTH))
    id = insert_submission(conn, {
        'fingerprint': TEST_1C_FP_RAW,
        'length': TEST_1C_LENGTH,
        'source_id': 1,
        'mbid': '1f143d2b-db04-47cc-82a0-eee6efaa1142',
        'puid': '7c1c6753-c834-44b1-884a-a5166c093139',
    })
    query = tables.submission.select(tables.submission.c.id == id)
    submission = conn.execute(query).fetchone()
    assert_false(submission['handled'])
    try:
        old_threshold = const.FINGERPRINT_MERGE_THRESHOLD
        const.FINGERPRINT_MERGE_THRESHOLD = 0.95
        fingerprint = import_submission(conn, submission)
    finally:
        const.FINGERPRINT_MERGE_THRESHOLD = old_threshold
    assert_equals(2, fingerprint['id'])
    assert_equals(1, fingerprint['track_id'])


@with_database
def test_import_submission_new_track(conn):
    prepare_database(conn, """
    INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
        VALUES (%(fp)s, %(len)s, 1, 1);
    """, dict(fp=TEST_1A_FP_RAW, len=TEST_1A_LENGTH))
    id = insert_submission(conn, {
        'fingerprint': TEST_1D_FP_RAW,
        'length': TEST_1D_LENGTH,
        'source_id': 1,
        'mbid': '1f143d2b-db04-47cc-82a0-eee6efaa1142',
        'puid': '7c1c6753-c834-44b1-884a-a5166c093139',
    })
    query = tables.submission.select(tables.submission.c.id == id)
    submission = conn.execute(query).fetchone()
    assert_false(submission['handled'])
    try:
        old_threshold = const.TRACK_MERGE_THRESHOLD
        const.TRACK_MERGE_THRESHOLD = 0.9
        fingerprint = import_submission(conn, submission)
    finally:
        const.TRACK_MERGE_THRESHOLD = old_threshold
    assert_equals(2, fingerprint['id'])
    assert_equals(5, fingerprint['track_id'])


@with_database
def test_import_submission_new_track_different(conn):
    prepare_database(conn, """
    INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
        VALUES (%(fp)s, %(len)s, 1, 1);
    """, dict(fp=TEST_1A_FP_RAW, len=TEST_1A_LENGTH))
    id = insert_submission(conn, {
        'fingerprint': TEST_2_FP_RAW,
        'length': TEST_2_LENGTH,
        'source_id': 1,
        'mbid': '1f143d2b-db04-47cc-82a0-eee6efaa1142',
        'puid': '7c1c6753-c834-44b1-884a-a5166c093139',
    })
    query = tables.submission.select(tables.submission.c.id == id)
    submission = conn.execute(query).fetchone()
    assert_false(submission['handled'])
    fingerprint = import_submission(conn, submission)
    assert_equals(2, fingerprint['id'])
    assert_equals(5, fingerprint['track_id'])


@with_database
def test_import_submission_merge_existing_tracks(conn):
    prepare_database(conn, """
    INSERT INTO fingerprint (fingerprint, length, track_id, submission_count)
        VALUES (%(fp1)s, %(len1)s, 1, 1), (%(fp2)s, %(len2)s, 2, 1);
    """, dict(fp1=TEST_1A_FP_RAW, len1=TEST_1A_LENGTH,
              fp2=TEST_1B_FP_RAW, len2=TEST_1B_LENGTH))
    id = insert_submission(conn, {
        'fingerprint': TEST_1C_FP_RAW,
        'length': TEST_1C_LENGTH,
        'source_id': 1,
        'mbid': '1f143d2b-db04-47cc-82a0-eee6efaa1142',
        'puid': '7c1c6753-c834-44b1-884a-a5166c093139',
    })
    query = tables.submission.select(tables.submission.c.id == id)
    submission = conn.execute(query).fetchone()
    assert_false(submission['handled'])
    try:
        old_threshold = const.FINGERPRINT_MERGE_THRESHOLD
        const.FINGERPRINT_MERGE_THRESHOLD = 0.85
        fingerprint = import_submission(conn, submission)
    finally:
        const.FINGERPRINT_MERGE_THRESHOLD = old_threshold
    assert_equals(1, fingerprint['id'])
    assert_equals(1, fingerprint['track_id'])
    query = tables.fingerprint.select(tables.fingerprint.c.id == 1)
    fingerprint = conn.execute(query).fetchone()
    assert_equals(1, fingerprint['track_id'])
    query = tables.track.select(tables.track.c.id == 1)
    track = conn.execute(query).fetchone()
    assert_equals(None, track['new_id'])
    query = tables.track.select(tables.track.c.id == 2)
    track = conn.execute(query).fetchone()
    assert_equals(1, track['new_id'])


@with_database
def test_import_queued_submissions(conn):
    insert_meta(conn, {'track': 'Foo'})
    insert_submission(conn, {
        'fingerprint': TEST_1_FP_RAW,
        'length': TEST_1_LENGTH,
        'bitrate': 192,
        'source_id': 1,
        'format_id': 1,
        'meta_id': 1,
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
